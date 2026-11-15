import type { Metadata } from "next";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";
import "./earth.css";
import SiteShell from "@/components/earth/shell";

export const metadata: Metadata = {
  title: "Earth Detective | Environmental Intelligence",
  description: "Scientific geospatial exploration of the August 2022 Sindh floods using real NASA observations and attributed hydrological data.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><SiteShell>{children}</SiteShell></body></html>;
}
