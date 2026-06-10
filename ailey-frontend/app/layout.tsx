import type React from "react"
import { Inter, Roboto_Mono } from "next/font/google"
import "./globals.css"
import "./rainbowpunk.css"
import "./ailey-theme.css"

const geistSans = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-geist-sans",
})

const geistMono = Roboto_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-geist-mono",
})

export const metadata = {
  title: "A!ley 2.5.0 – Digital Consciousness",
  description:
    "A!ley – Local-first AI companion with personality, memory & RAG. Punk rock meets digital consciousness.",
}

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
      <body>{children}</body>
    </html>
  )
}
