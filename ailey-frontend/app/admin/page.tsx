"use client"
import { useEffect, useState } from "react"

export default function AdminPage() {
  const [users, setUsers] = useState<string[]>([])
  const [system, setSystem] = useState<any>(null)

  useEffect(() => {
    const run = async () => {
      try {
        const u = await fetch("/api/admin/users").then(r=>r.json())
        if (u?.success) setUsers(u.users||[])
        const s = await fetch("/api/admin/system").then(r=>r.json())
        if (s?.success) setSystem(s)
      } catch(e) {}
    }
    run()
  }, [])

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-4">Admin</h1>
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-2">System</h2>
        <pre className="text-sm bg-black/10 p-3 rounded">{JSON.stringify(system, null, 2)}</pre>
      </div>
      <div>
        <h2 className="text-xl font-semibold mb-2">Users</h2>
        <ul className="list-disc pl-5">
          {users.map(u => (<li key={u}>{u}</li>))}
        </ul>
      </div>
    </div>
  )
}
