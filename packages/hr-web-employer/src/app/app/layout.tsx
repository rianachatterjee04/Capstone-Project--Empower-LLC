export const dynamic = 'force-dynamic';
import { AppShell } from '@/components/AppShell';
export default function AppLayout({ children }: { children: React.ReactNode }) { return <AppShell>{children}</AppShell>; }
