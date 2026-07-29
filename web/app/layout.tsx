import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import NavBar from "@/components/NavBar";
import AuthTokenCapture from "@/components/AuthTokenCapture";

export const metadata: Metadata = {
  title: "War Queue",
  description: "Queue up, form a group, and get matched for wars.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-bg text-fg antialiased">
        <Suspense fallback={null}>
          <AuthTokenCapture />
        </Suspense>
        <NavBar />
        {children}
      </body>
    </html>
  );
}
