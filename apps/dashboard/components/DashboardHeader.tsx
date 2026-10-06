import Link from 'next/link';
import IntegrationsHelpButton from '@/components/IntegrationsHelpButton';
import NavLink from '@/components/NavLink';
import MobileNav from '@/components/MobileNav';
import { getBranding } from '@/utils/branding';

export default function DashboardHeader() {
  const showChat = process.env.SHOW_CHAT === 'true';
  const branding = getBranding();

  return (
    <header className="relative bg-brand">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 flex items-center justify-between h-16">
        <div className="flex items-center gap-3">
          <MobileNav showChat={showChat} />
          <Link href="/" className="shrink-0">
            <span className="text-white font-semibold text-lg whitespace-nowrap">{branding.appName}</span>
          </Link>
        </div>

        <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
          <NavLink href="/" onDark>Responses</NavLink>
          <NavLink href="/analytics" onDark>Analytics</NavLink>
          {showChat && <NavLink href="/chat" onDark>Chat</NavLink>}
        </nav>

        <div className="flex items-center gap-2 shrink-0">
          <IntegrationsHelpButton />
        </div>
      </div>
    </header>
  );
}
