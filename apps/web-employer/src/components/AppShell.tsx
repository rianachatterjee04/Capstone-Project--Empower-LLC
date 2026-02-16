"use client";
import { Sidebar } from './Sidebar';
export function AppShell({ children }: { children: React.ReactNode }) { return (<div className='min-h-screen bg-white text-black'><div className='flex'><Sidebar /><main className='flex-1 p-6'>{children}</main></div></div>); }
