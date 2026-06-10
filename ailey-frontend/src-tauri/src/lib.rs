use std::process::{Child, Command};
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};

// Global handle to caffeinate process (prevents macOS sleep while Ailey runs)
static CAFFEINATE_PROCESS: Mutex<Option<Child>> = Mutex::new(None);

// Track whether WE started the backend (via Remote Controller)
static WE_OWN_BACKEND: AtomicBool = AtomicBool::new(false);

// Store the PID of the backend process we spawned (0 = none)
static BACKEND_PID: AtomicU32 = AtomicU32::new(0);

// Guard against double-stop (CloseRequested + RunEvent::Exit)
static STOP_CALLED: AtomicBool = AtomicBool::new(false);

// Fixed path to the Ailey project (since you're the only user)
const AILEY_BASE_PATH: &str = "/Users/simonvandeloo/Ailey-Workspace/Ailey-2.0 Core";
const REMOTE_PORT: u16 = 5580;
const BACKEND_PORT: u16 = 5502;

/// Start `caffeinate` to prevent macOS from sleeping (idle, system, disk)
fn start_caffeinate() {
    stop_caffeinate();
    match Command::new("caffeinate").args(["-ims"]).spawn() {
        Ok(child) => {
            println!("[caffeinate] Started (PID {}), macOS sleep prevention active", child.id());
            *CAFFEINATE_PROCESS.lock().unwrap() = Some(child);
        }
        Err(e) => {
            eprintln!("[caffeinate] Failed to start: {} — Mac may sleep normally", e);
        }
    }
}

/// Stop the caffeinate process
fn stop_caffeinate() {
    if let Some(mut child) = CAFFEINATE_PROCESS.lock().unwrap().take() {
        println!("[caffeinate] Stopping (PID {})", child.id());
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// Check if a port is listening
fn is_port_open(port: u16) -> bool {
    std::net::TcpStream::connect_timeout(
        &format!("127.0.0.1:{}", port).parse().unwrap(),
        std::time::Duration::from_millis(500),
    ).is_ok()
}

/// Simple HTTP GET request via curl (no external Rust dependencies needed)
fn http_get(url: &str) -> Result<String, String> {
    let output = Command::new("curl")
        .args(["-s", "-m", "10", url])
        .output()
        .map_err(|e| format!("curl failed: {}", e))?;
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

/// Ensure the Remote Controller is running (it's a LaunchAgent, should auto-start)
fn ensure_remote_controller() -> Result<(), String> {
    if is_port_open(REMOTE_PORT) {
        println!("[Tauri] Remote Controller already running on port {}", REMOTE_PORT);
        return Ok(());
    }

    println!("[Tauri] Remote Controller not running — starting LaunchAgent...");
    let plist = format!("{}/de.hinterhofagentur.ailey.remote.plist", AILEY_BASE_PATH);
    let _ = Command::new("launchctl").args(["load", "-w", &plist]).output();

    // Wait for it to come up (max 10 seconds)
    for i in 0..20 {
        if is_port_open(REMOTE_PORT) {
            println!("[Tauri] Remote Controller ready after {}ms", i * 500);
            return Ok(());
        }
        std::thread::sleep(std::time::Duration::from_millis(500));
    }

    Err("Remote Controller did not start within 10 seconds".to_string())
}

fn start_backend() -> Result<(), String> {
    // ── 1. Check if backend is already running (port OR PID file) ──
    if is_port_open(BACKEND_PORT) {
        println!("[Tauri] Backend already running on port {}", BACKEND_PORT);
        WE_OWN_BACKEND.store(false, Ordering::SeqCst);
        start_caffeinate();
        return Ok(());
    }

    // Check PID file — the API writes this immediately on startup,
    // BEFORE Flask binds the port (heavy init takes 20-40s).
    let pid_file = format!("{}/ailey_api.pid", AILEY_BASE_PATH);
    if let Ok(pid_str) = std::fs::read_to_string(&pid_file) {
        if let Ok(pid) = pid_str.trim().parse::<i32>() {
            // Check if that PID is still alive (signal 0 = just check)
            if unsafe { libc::kill(pid, 0) } == 0 {
                println!("[Tauri] Backend already booting (PID {} from pid file, port not yet open)", pid);
                BACKEND_PID.store(pid as u32, Ordering::SeqCst);
                WE_OWN_BACKEND.store(true, Ordering::SeqCst);
                start_caffeinate();
                // Wait for port to come up (it's already booting)
                return wait_for_backend();
            } else {
                // Stale PID file — process is dead, remove it
                println!("[Tauri] Stale PID file (PID {} is dead) — removing", pid);
                let _ = std::fs::remove_file(&pid_file);
            }
        }
    }

    // 2. Start caffeinate
    start_caffeinate();

    // 3. Start the backend DIRECTLY (no Remote Controller dependency)
    println!("[Tauri] Starting backend directly...");
    let python_path = format!("{}/.venv/bin/python", AILEY_BASE_PATH);
    let api_path = format!("{}/ailey_api.py", AILEY_BASE_PATH);
    let log_path = format!("{}/api_run.log", AILEY_BASE_PATH);
    
    // Open log file for stdout/stderr redirect (so we can actually see errors)
    let log_file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path);
    
    let mut cmd = Command::new(&python_path);
    cmd.arg(&api_path)
        .current_dir(AILEY_BASE_PATH)
        // ── CRITICAL: Set environment variables to prevent Errno 11 ──
        // macOS ObjC Fork Safety blocks fork() when Objective-C runtime
        // is already initialized (launchd → Tauri → Python → loky/joblib).
        // Without these, importing Flask in the subprocess triggers EDEADLK.
        .env("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
        .env("LOKY_MAX_CPU_COUNT", "1")
        .env("TOKENIZERS_PARALLELISM", "false")
        .env("JOBLIB_MULTIPROCESSING", "0")
        .env("no_proxy", "*")
        .env("PYTHONUNBUFFERED", "1")
        // Ensure PATH includes Homebrew AND /usr/sbin (needed for system_profiler by mflux)
        .env("PATH", format!(
            "{}/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin",
            AILEY_BASE_PATH
        ));
    
    // Redirect to log file if possible, otherwise /dev/null
    match log_file {
        Ok(f) => {
            let f2 = f.try_clone().unwrap_or_else(|_| {
                std::fs::OpenOptions::new()
                    .create(true).append(true).open(&log_path).unwrap()
            });
            cmd.stdout(std::process::Stdio::from(f))
               .stderr(std::process::Stdio::from(f2));
        }
        Err(_) => {
            cmd.stdout(std::process::Stdio::null())
               .stderr(std::process::Stdio::null());
        }
    }
    
    match cmd.spawn()
    {
        Ok(child) => {
            let pid = child.id();
            println!("[Tauri] Backend process started (PID {})", pid);
            BACKEND_PID.store(pid, Ordering::SeqCst);
            WE_OWN_BACKEND.store(true, Ordering::SeqCst);
        }
        Err(e) => {
            eprintln!("[Tauri] Failed to start backend directly: {}", e);
            // Fallback: try Remote Controller
            println!("[Tauri] Falling back to Remote Controller...");
            if is_port_open(REMOTE_PORT) {
                let _ = http_get(&format!("http://127.0.0.1:{}/start", REMOTE_PORT));
                WE_OWN_BACKEND.store(true, Ordering::SeqCst);
            } else {
                return Err(format!("Cannot start backend: {}", e));
            }
        }
    }

    // 4. Wait for the backend to become available
    wait_for_backend()
}

fn wait_for_backend() -> Result<(), String> {
    // Wait max 90s — model loading + SentenceTransformer can take 30-60s
    println!("[Tauri] Waiting for backend to initialize...");
    for i in 0..180 {
        if is_port_open(BACKEND_PORT) {
            println!("[Tauri] Backend ready after {}ms", i * 500);
            return Ok(());
        }
        std::thread::sleep(std::time::Duration::from_millis(500));
        if i == 10 {
            println!("[Tauri] (loading model — this can take 30-60 seconds)");
        }
        if i == 60 {
            println!("[Tauri] (still loading — SentenceTransformer + MLX models)");
        }
        // Safety: check if the process is still alive
        let pid = BACKEND_PID.load(Ordering::SeqCst);
        if pid > 0 && i > 10 && i % 10 == 0 {
            let alive = unsafe { libc::kill(pid as i32, 0) } == 0;
            if !alive {
                println!("[Tauri] Backend process PID {} died during startup!", pid);
                BACKEND_PID.store(0, Ordering::SeqCst);
                return Err("Backend process died during startup".to_string());
            }
        }
    }

    // Even if we timed out, don't fail — the frontend has a splash/loading state
    println!("[Tauri] Backend not yet responding, continuing (model may still be loading)");
    Ok(())
}

fn stop_backend() {
    // ── Guard: only run once (both CloseRequested AND RunEvent::Exit fire) ──
    if STOP_CALLED.swap(true, Ordering::SeqCst) {
        println!("[Tauri] stop_backend() already called — skipping");
        return;
    }

    // Release caffeinate
    stop_caffeinate();

    // If we didn't start it, leave it running
    if !WE_OWN_BACKEND.load(Ordering::SeqCst) {
        println!("[Tauri] Backend was not started by us — leaving it running");
        return;
    }

    // ── Kill by stored PID (precise, no collateral damage) ──
    let pid = BACKEND_PID.swap(0, Ordering::SeqCst);
    if pid > 0 {
        println!("[Tauri] Stopping backend PID {}...", pid);
        unsafe { libc::kill(pid as i32, libc::SIGTERM); }
        // Give it 3 seconds to shut down gracefully, then force-kill
        std::thread::sleep(std::time::Duration::from_secs(3));
        // Check if still alive
        let alive = unsafe { libc::kill(pid as i32, 0) } == 0;
        if alive {
            println!("[Tauri] Backend PID {} still alive — sending SIGKILL", pid);
            unsafe { libc::kill(pid as i32, libc::SIGKILL); }
        } else {
            println!("[Tauri] Backend PID {} exited cleanly", pid);
        }
    } else {
        println!("[Tauri] No backend PID stored — nothing to kill");
    }

    // Clean up PID file
    let pid_file = format!("{}/ailey_api.pid", AILEY_BASE_PATH);
    let _ = std::fs::remove_file(&pid_file);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|_app| {
            // Start backend in background thread so the window opens immediately
            std::thread::spawn(|| {
                if let Err(e) = start_backend() {
                    eprintln!("Backend start error: {}", e);
                }
            });
            Ok(())
        })
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                stop_backend();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                stop_backend();
            }
        });
}
