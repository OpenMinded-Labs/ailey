# React & TSX — Ailey Code-Referenz

> Modern React 18+/19 mit TypeScript, Hooks, Server Components, Next.js Patterns

## Projekt-Setup
```bash
# Next.js (empfohlen)
npx create-next-app@latest my-app --typescript --tailwind --app --src-dir

# Vite (SPA)
npm create vite@latest my-app -- --template react-ts
```

## Komponenten-Patterns

### Funktionale Komponente (Standard)
```tsx
interface Props {
  title: string;
  count?: number;
  onAction: (id: string) => void;
  children?: React.ReactNode;
}

export function Card({ title, count = 0, onAction, children }: Props) {
  return (
    <div className="rounded-lg border p-4">
      <h3>{title} ({count})</h3>
      <button onClick={() => onAction(title)}>Aktion</button>
      {children}
    </div>
  );
}
```

### Hooks (die wichtigsten)
```tsx
import { useState, useEffect, useRef, useCallback, useMemo } from 'react';

function Example() {
  // State
  const [items, setItems] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  // Ref (DOM oder Werte die kein Re-Render auslösen)
  const inputRef = useRef<HTMLInputElement>(null);

  // Effect (Side Effects, Fetch, Subscriptions)
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/items', { signal: controller.signal })
      .then(r => r.json())
      .then(data => setItems(data));
    return () => controller.abort(); // Cleanup!
  }, []); // [] = einmal beim Mount

  // Callback (stabile Referenz)
  const handleAdd = useCallback((item: string) => {
    setItems(prev => [...prev, item]);
  }, []);

  // Memo (teure Berechnung cachen)
  const sorted = useMemo(() => 
    [...items].sort(), [items]
  );
}
```

### Custom Hooks
```tsx
function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === 'undefined') return initial;
    const stored = localStorage.getItem(key);
    return stored ? JSON.parse(stored) : initial;
  });

  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);

  return [value, setValue] as const;
}

// Verwendung
const [theme, setTheme] = useLocalStorage('theme', 'dark');
```

## Next.js App Router

### Server Component (Standard — kein "use client")
```tsx
// app/users/page.tsx — Server Component
async function UsersPage() {
  const users = await fetch('https://api.example.com/users', {
    next: { revalidate: 60 } // ISR: alle 60s
  }).then(r => r.json());

  return (
    <div>
      <h1>Users</h1>
      {users.map((u: any) => <UserCard key={u.id} user={u} />)}
    </div>
  );
}
export default UsersPage;
```

### Client Component
```tsx
"use client"; // MUSS erste Zeile sein!

import { useState } from 'react';

export function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(c => c + 1)}>Count: {count}</button>;
}
```

### Layout & Metadata
```tsx
// app/layout.tsx
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'My App',
  description: 'Description',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
```

### API Route (Route Handler)
```tsx
// app/api/items/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({ items: [] });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  return NextResponse.json({ success: true }, { status: 201 });
}
```

## TypeScript Patterns

```tsx
// Union Types für Status
type Status = 'idle' | 'loading' | 'success' | 'error';

// Generics
function useAsync<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  // ...
}

// Type Guards
function isError(result: Success | Error): result is Error {
  return 'error' in result;
}

// Utility Types
type Partial<T>     // alle Props optional
type Required<T>    // alle Props required
type Pick<T, K>     // nur bestimmte Props
type Omit<T, K>     // alle außer bestimmte Props
type Record<K, V>   // Key-Value Mapping
```

## Tailwind CSS (mit React)
```tsx
// Conditional Classes
<div className={`p-4 rounded ${active ? 'bg-blue-500 text-white' : 'bg-gray-100'}`}>

// Mit clsx/cn (empfohlen)
import { cn } from '@/lib/utils';
<div className={cn('p-4 rounded', active && 'bg-blue-500', className)}>
```

## State Management
```tsx
// Einfach: Context + useReducer
const ThemeContext = React.createContext<{theme: string; toggle: () => void}>(null!);

// Komplex: Zustand (empfohlen über Redux)
import { create } from 'zustand';

const useStore = create<{count: number; inc: () => void}>((set) => ({
  count: 0,
  inc: () => set((s) => ({ count: s.count + 1 })),
}));
```

## Häufige Stolperfallen
- `"use client"` vergessen → Hooks gehen nicht in Server Components
- Key-Prop fehlt in `.map()` → React warnt, Performance-Problem
- useEffect Cleanup vergessen → Memory Leaks, Race Conditions
- State-Update in Render → Infinite Loop
- `===` statt `==` verwenden (TypeScript hilft hier)
- Next.js: `Image` statt `<img>`, `Link` statt `<a>`
