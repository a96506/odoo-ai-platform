import "./globals.css";

export const metadata = {
  title: "Odoo AI Automation Dashboard",
  description: "Monitor and manage AI-powered automations for Odoo ERP",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 min-h-screen">{children}</body>
    </html>
  );
}
