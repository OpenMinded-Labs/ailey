# Rust — Ailey Code-Referenz

> Rust 2021 Edition — Safety, Performance, Ownership, Traits, Async

## Projekt-Setup

```bash
# Neues Projekt
cargo new my_project        # Binary
cargo new my_lib --lib       # Library

# Workspace
cargo new workspace_name
```

```
my_project/
├── src/
│   ├── main.rs             # Binary entry point
│   ├── lib.rs              # Library entry point
│   └── models/
│       └── mod.rs
├── tests/
│   └── integration_test.rs
├── benches/
├── Cargo.toml
└── .gitignore
```

## Cargo.toml

```toml
[package]
name = "my-project"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
anyhow = "1"           # Einfaches Error Handling
thiserror = "1"         # Custom Error Types
reqwest = { version = "0.12", features = ["json"] }

[dev-dependencies]
pretty_assertions = "1"
```

## Ownership & Borrowing

```rust
fn main() {
    // Ownership — jeder Wert hat genau einen Owner
    let s1 = String::from("hello");
    let s2 = s1;          // s1 ist jetzt MOVED, nicht mehr nutzbar
    // println!("{s1}");   // Compile Error!
    
    // Borrowing — Referenzen leihen
    let s = String::from("hello");
    let len = calculate_length(&s);  // Immutable Borrow
    println!("{s} has length {len}"); // s ist noch nutzbar
    
    // Mutable Borrow — nur EINE gleichzeitig
    let mut s = String::from("hello");
    change(&mut s);
    
    // Lifetimes (explizit wenn nötig)
    fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
        if x.len() > y.len() { x } else { y }
    }
}

fn calculate_length(s: &str) -> usize { s.len() }
fn change(s: &mut String) { s.push_str(" world"); }
```

## Structs & Enums

```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
struct User {
    id: u64,
    name: String,
    email: String,
    #[serde(default)]
    active: bool,
}

impl User {
    fn new(name: impl Into<String>, email: impl Into<String>) -> Self {
        Self {
            id: 0,
            name: name.into(),
            email: email.into(),
            active: true,
        }
    }
    
    fn display_name(&self) -> &str {
        &self.name
    }
}

// Enums mit Daten (Algebraische Datentypen)
#[derive(Debug)]
enum AppError {
    NotFound(String),
    Unauthorized,
    Database(String),
    Internal(anyhow::Error),
}

impl std::fmt::Display for AppError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotFound(msg) => write!(f, "Not found: {msg}"),
            Self::Unauthorized => write!(f, "Unauthorized"),
            Self::Database(msg) => write!(f, "DB error: {msg}"),
            Self::Internal(e) => write!(f, "Internal: {e}"),
        }
    }
}
```

## Traits

```rust
trait Summary {
    fn summarize(&self) -> String;
    
    // Default Implementation
    fn preview(&self) -> String {
        format!("{}...", &self.summarize()[..50.min(self.summarize().len())])
    }
}

impl Summary for User {
    fn summarize(&self) -> String {
        format!("{} ({})", self.name, self.email)
    }
}

// Generics mit Trait Bounds
fn print_summary(item: &impl Summary) {
    println!("{}", item.summarize());
}

// Oder explizit
fn process<T: Summary + Clone>(items: &[T]) -> Vec<String> {
    items.iter().map(|i| i.summarize()).collect()
}
```

## Error Handling

```rust
use anyhow::{Context, Result};
use thiserror::Error;

// Custom Error mit thiserror
#[derive(Error, Debug)]
enum MyError {
    #[error("File not found: {0}")]
    NotFound(String),
    #[error("Parse error")]
    Parse(#[from] serde_json::Error),
    #[error("IO error")]
    Io(#[from] std::io::Error),
}

// Mit anyhow (einfach)
fn read_config(path: &str) -> Result<Config> {
    let content = std::fs::read_to_string(path)
        .context(format!("Failed to read {path}"))?;
    let config: Config = serde_json::from_str(&content)
        .context("Failed to parse config")?;
    Ok(config)
}

// Pattern Matching
match result {
    Ok(value) => println!("Success: {value}"),
    Err(e) => eprintln!("Error: {e}"),
}

// ? Operator — propagiert Fehler
let file = std::fs::File::open("data.json")?;
```

## Async / Tokio

```rust
use tokio;
use reqwest;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let response = reqwest::get("https://api.example.com/data")
        .await?
        .json::<Vec<User>>()
        .await?;
    
    println!("Got {} users", response.len());
    Ok(())
}

// Async Funktion
async fn fetch_user(id: u64) -> Result<User> {
    let url = format!("https://api.example.com/users/{id}");
    let user = reqwest::get(&url).await?.json::<User>().await?;
    Ok(user)
}

// Parallel Execution
let (users, posts) = tokio::join!(
    fetch_users(),
    fetch_posts(),
);
```

## Axum (Web Framework)

```rust
use axum::{
    extract::{Json, Path, State},
    http::StatusCode,
    routing::{get, post},
    Router,
};
use std::sync::Arc;
use tokio::sync::RwLock;

type AppState = Arc<RwLock<Vec<User>>>;

#[tokio::main]
async fn main() {
    let state: AppState = Arc::new(RwLock::new(vec![]));
    
    let app = Router::new()
        .route("/api/users", get(list_users).post(create_user))
        .route("/api/users/:id", get(get_user))
        .with_state(state);
    
    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

async fn list_users(State(state): State<AppState>) -> Json<Vec<User>> {
    let users = state.read().await;
    Json(users.clone())
}

async fn create_user(
    State(state): State<AppState>,
    Json(user): Json<User>,
) -> StatusCode {
    state.write().await.push(user);
    StatusCode::CREATED
}
```

## Iterators & Closures

```rust
let numbers = vec![1, 2, 3, 4, 5];

// Map, Filter, Collect
let doubled: Vec<i32> = numbers.iter().map(|n| n * 2).collect();
let evens: Vec<&i32> = numbers.iter().filter(|n| *n % 2 == 0).collect();
let sum: i32 = numbers.iter().sum();

// Chaining
let result: Vec<String> = items.iter()
    .filter(|i| i.active)
    .map(|i| i.name.clone())
    .take(10)
    .collect();

// find, any, all
let found = items.iter().find(|i| i.id == 42);
let has_admin = items.iter().any(|i| i.role == "admin");
```

## Testing

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_user_creation() {
        let user = User::new("Simon", "simon@example.com");
        assert_eq!(user.name, "Simon");
        assert!(user.active);
    }
    
    #[test]
    #[should_panic(expected = "empty name")]
    fn test_empty_name_panics() {
        User::new("", "test@example.com");
    }
    
    #[tokio::test]
    async fn test_async_fetch() {
        let result = fetch_user(1).await;
        assert!(result.is_ok());
    }
}
```

## Häufige Stolperfallen

- Ownership/Borrowing → `.clone()` wenn nötig, aber sparsam einsetzen
- `String` vs `&str` → Funktionen nehmen `&str`, Structs besitzen `String`
- `unwrap()` nie in Produktion → immer `?` oder `match` verwenden
- Lebensdauer-Fehler → oft hilft es, Daten zu clonen oder `Arc` zu nutzen
- `mut` vergessen → Compiler-Fehler, aber leicht zu fixen
- `cargo clippy` → zeigt idiomatischere Lösungen
- `cargo fmt` → einheitliche Formatierung
- Deadlocks mit `Mutex` → `RwLock` bevorzugen, Lock-Reihenfolge beachten
