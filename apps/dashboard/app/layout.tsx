import type { Metadata } from "next";
import { DM_Sans, Lora } from "next/font/google";
import { BrandingProvider } from "@/components/BrandingProvider";
import { getBranding } from "@/utils/branding";
import "./globals.css";

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
});

const lora = Lora({
  variable: "--font-lora",
  subsets: ["latin"],
});

export async function generateMetadata(): Promise<Metadata> {
  const branding = getBranding();
  return {
    title: `${branding.appName} Dashboard`,
    description: `Analytics dashboard for ${branding.appName}`,
    icons: {
      icon: branding.faviconPath,
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Branding applied at request time. Overriding the two
  // --brand-* custom properties here re-skins every `bg-brand` / `text-brand` usage without
  // touching components (they resolve through --color-brand -> --brand-blue).
  const branding = getBranding();
  const brandStyle = {
    "--brand-blue": branding.brandColor,
    "--brand-blue-dark": branding.brandColorDark,
  } as React.CSSProperties;
  return (
    <html lang="en">
      <body
        className={`${dmSans.variable} ${lora.variable} antialiased`}
        style={brandStyle}
      >
        <BrandingProvider value={branding}>
          {children}
        </BrandingProvider>
      </body>
    </html>
  );
}
