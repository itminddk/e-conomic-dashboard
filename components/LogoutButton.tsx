"use client";

import { useRouter } from "next/navigation";

export default function LogoutButton() {
  const router = useRouter();

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  return (
    <button
      onClick={logout}
      className="text-sm text-gray-500 hover:text-gray-800 transition-colors"
    >
      Log ud
    </button>
  );
}
