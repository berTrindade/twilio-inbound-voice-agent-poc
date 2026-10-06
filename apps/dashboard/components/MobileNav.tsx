'use client';

import { useState } from 'react';
import NavLink from '@/components/NavLink';

interface MobileNavProps {
  showChat: boolean;
}

export default function MobileNav({ showChat }: MobileNavProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="md:hidden">
      <button
        onClick={() => setOpen(!open)}
        className="p-2 rounded-md text-white hover:bg-white/10 transition-colors"
        aria-label={open ? 'Close menu' : 'Open menu'}
        aria-expanded={open}
      >
        {open ? (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
          </svg>
        )}
      </button>

      {open && (
        <nav
          className="absolute left-0 right-0 top-full z-20 bg-white border-b border-gray-200 shadow-lg px-4 py-3 flex flex-col gap-1"
          aria-label="Mobile navigation"
          onClick={() => setOpen(false)}
        >
          <NavLink href="/">Responses</NavLink>
          <NavLink href="/analytics">Analytics</NavLink>
          {showChat && <NavLink href="/chat">Chat</NavLink>}
        </nav>
      )}
    </div>
  );
}
