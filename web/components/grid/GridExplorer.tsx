"use client";
// Compatibility wrapper. The previous component is preserved by INSTALL_UI.ps1
// under .ui_backups before replacement, including any local modifications.
import { ExplorerPage } from "@/components/earth/pages";
export default function GridExplorer(){return <ExplorerPage/>;}
