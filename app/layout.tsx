import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "散户温度计｜A股社区情绪",
    template: "%s",
  },
  description: "观察 A 股行情、板块轮动与公开社区表达，分别展示数据时效、采样覆盖和计算依据。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
