import type { Metadata } from "next";
import Script from "next/script";

export const metadata: Metadata = {
  title: "TierceMsg",
  description: "Multi-tenant WhatsApp engagement platform",
};

const META_APP_ID = process.env.NEXT_PUBLIC_META_APP_ID ?? "";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {children}

        {/*
          Meta (Facebook) JS SDK — loaded once for the entire app.
          afterInteractive: loads after page is interactive (correct for popups).
          The fbAsyncInit callback initializes FB with your App ID.
        */}
        <Script id="facebook-jssdk-init" strategy="afterInteractive">
          {`
            window.fbAsyncInit = function() {
              FB.init({
                appId            : '${META_APP_ID}',
                autoLogAppEvents : true,
                xfbml            : true,
                version          : 'v25.0'
              });
            };
          `}
        </Script>
        <Script
          id="facebook-jssdk"
          src="https://connect.facebook.net/en_US/sdk.js"
          strategy="afterInteractive"
          crossOrigin="anonymous"
          async
          defer
        />
      </body>
    </html>
  );
}
