"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const navLinks = [
  { href: "/", label: "Home" },
  { href: "/install", label: "Install" },
  { href: "/usage", label: "Usage" },
  { href: "/plugins", label: "Plugins" },
];

export default function Navigation() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md bg-canvas/80 border-b border-border">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 group">
            <div className="relative">
              <div className="w-3 h-3 rounded-full bg-secondary pulse-dot" />
            </div>
            <span className="text-xl font-light tracking-tight text-text-primary group-hover:text-primary-light transition-colors duration-300">
              Jarvix
            </span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-1 bg-surface rounded-full px-2 py-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-300 ${
                  pathname === link.href
                    ? "bg-primary text-white shadow-lg shadow-primary/20"
                    : "text-text-muted hover:text-text-primary hover:bg-card"
                }`}
              >
                {link.label}
              </Link>
            ))}
          </div>

          {/* CTA Button */}
          <div className="hidden md:flex items-center gap-3">
            <Link
              href="https://github.com/jarvix/jarvix"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 rounded-lg border border-border text-text-muted hover:border-primary hover:text-primary transition-all duration-300 text-sm"
            >
              GitHub
            </Link>
            <Link
              href="/install"
              className="px-4 py-2 rounded-lg bg-primary text-white hover:bg-primary-light transition-all duration-300 text-sm font-medium shadow-lg shadow-primary/20"
            >
              Get Started
            </Link>
          </div>

          {/* Mobile menu button */}
          <button
            className="md:hidden p-2 text-text-muted hover:text-text-primary transition-colors"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Toggle menu"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              {mobileOpen ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              )}
            </svg>
          </button>
        </div>

        {/* Mobile menu */}
        {mobileOpen && (
          <div className="md:hidden mt-4 pb-4 border-t border-border pt-4">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className={`block px-4 py-3 rounded-lg text-sm font-medium transition-all duration-300 ${
                  pathname === link.href
                    ? "bg-primary/10 text-primary"
                    : "text-text-muted hover:text-text-primary hover:bg-card"
                }`}
              >
                {link.label}
              </Link>
            ))}
            <div className="mt-4 px-4 flex flex-col gap-2">
              <Link
                href="https://github.com/jarvix/jarvix"
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 rounded-lg border border-border text-text-muted hover:border-primary hover:text-primary transition-all duration-300 text-sm text-center"
              >
                GitHub
              </Link>
              <Link
                href="/install"
                className="px-4 py-2 rounded-lg bg-primary text-white hover:bg-primary-light transition-all duration-300 text-sm font-medium text-center"
              >
                Get Started
              </Link>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
