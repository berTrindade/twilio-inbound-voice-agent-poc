'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

interface NavLinkProps {
  href: string;
  children: React.ReactNode;
  onDark?: boolean;
}

export default function NavLink({ href, children, onDark = false }: NavLinkProps) {
  const pathname = usePathname();
  const isActive = pathname === href;

  const darkStyles = isActive
    ? 'bg-white/20 text-white font-semibold'
    : 'text-white/80 hover:bg-white/10 hover:text-white';

  const lightStyles = isActive
    ? 'bg-brand/10 text-brand'
    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900';

  return (
    <Link
      href={href}
      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
        onDark ? darkStyles : lightStyles
      }`}
    >
      {children}
    </Link>
  );
}
