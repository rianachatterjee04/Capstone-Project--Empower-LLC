"use client";
/**
 * Manager OS — promoted to the manager's landing surface.
 *
 * This route now renders the same "Who needs my attention today" home a
 * manager lands on at /app. The old demo manager-selector is gone: the brief
 * is scoped to the signed-in manager's own team.
 */
import { ManagerHome } from "@/components/homes/ManagerHome";

export default function ManagerOSPage() {
  return <ManagerHome />;
}
