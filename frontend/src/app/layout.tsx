import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "StreamClip AI — Dashboard",
  description: "Autonomous stream highlight pipeline — monitor streams, review clips, manage uploads",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
      </body>
    </html>
  );
}
