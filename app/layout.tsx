import type { Metadata } from "next";
import "./globals.css";
import LogoutButton from "@/components/LogoutButton";
import { cookies } from "next/headers";
import { verifyToken, COOKIE } from "@/lib/auth";

export const metadata: Metadata = {
  title: "E-conomic Dashboard",
  description: "Overblik over regnskabstal fra e-conomic",
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies();
  const token = cookieStore.get(COOKIE)?.value;
  const isLoggedIn = token ? await verifyToken(token) : false;

  return (
    <html lang="da">
      <body className="bg-gray-50 text-gray-900 antialiased">
        <header className="bg-white border-b border-gray-200 px-4 py-3 sm:px-6 sm:py-4">
          <div className="max-w-6xl mx-auto flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shrink-0">
                <span className="text-white font-bold text-sm">E</span>
              </div>
              <h1 className="text-base sm:text-lg font-semibold">E-conomic Dashboard</h1>
            </div>
            {isLoggedIn && <LogoutButton />}
          </div>
        </header>
        <main className="max-w-6xl mx-auto px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      </body>
    </html>
  );
}
