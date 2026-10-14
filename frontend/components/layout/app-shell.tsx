"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Files, MessageSquareText, Sparkles } from "lucide-react"
import { Suspense } from "react"

import { SessionNavigation } from "@/components/layout/session-navigation"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"

const navigationItems = [
  {
    href: "/chat",
    label: "Chat",
    icon: MessageSquareText,
  },
  {
    href: "/documents",
    label: "Tài liệu",
    icon: Files,
  },
] as const

function matchesRoute(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`)
}

function NavigationLinks({ pathname }: { pathname?: string }) {
  const { isMobile, setOpenMobile } = useSidebar()

  return (
    <nav aria-label="Điều hướng chính">
      <SidebarGroup>
        <SidebarGroupLabel>Không gian làm việc</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            {navigationItems.map((item) => {
              const isActive = pathname ? matchesRoute(pathname, item.href) : false
              const Icon = item.icon

              return (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    isActive={isActive}
                    tooltip={item.label}
                    render={
                      <Link
                        href={item.href}
                        aria-current={isActive ? "page" : undefined}
                        onClick={() => {
                          if (isMobile) setOpenMobile(false)
                        }}
                      />
                    }
                  >
                    <Icon aria-hidden="true" />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              )
            })}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </nav>
  )
}

function AppNavigation() {
  const pathname = usePathname()

  return <NavigationLinks pathname={pathname} />
}

function AppSidebar({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  const { isMobile, setOpenMobile } = useSidebar()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-3">
        <Link
          href="/chat"
          className="flex min-h-10 items-center gap-3 rounded-lg px-2 outline-none ring-sidebar-ring transition-colors hover:bg-sidebar-accent focus-visible:ring-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
          onClick={() => {
            if (isMobile) setOpenMobile(false)
          }}
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
            <Sparkles className="size-4" aria-hidden="true" />
          </span>
          <span className="min-w-0 leading-tight group-data-[collapsible=icon]:hidden">
            <span className="block truncate text-sm font-semibold">RAG Workspace</span>
            <span className="block truncate text-xs text-sidebar-foreground/65">
              Trợ lý tài liệu
            </span>
          </span>
        </Link>
      </SidebarHeader>
      <SidebarSeparator />
      <SidebarContent>
        <Suspense fallback={<NavigationLinks />}>
          <AppNavigation />
        </Suspense>
        <SidebarSeparator />
        <SessionNavigation apiBaseUrl={apiBaseUrl} />
      </SidebarContent>
      <SidebarFooter className="p-3">
        <p className="px-2 text-xs leading-5 text-sidebar-foreground/60 group-data-[collapsible=icon]:hidden">
          Nhấn Ctrl/Cmd+B để thu gọn thanh bên.
        </p>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}

function getRouteLabel(pathname: string) {
  if (matchesRoute(pathname, "/documents")) return "Tài liệu"
  return "Chat"
}

function RouteLabel() {
  const pathname = usePathname()

  return <>{getRouteLabel(pathname)}</>
}

export function AppShell({ children, apiBaseUrl }: { children: React.ReactNode; apiBaseUrl: string | null }) {
  return (
    <SidebarProvider>
      <AppSidebar apiBaseUrl={apiBaseUrl} />
      <SidebarInset id="main-content" tabIndex={-1} className="min-h-svh min-w-0">
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b bg-background/95 px-3 backdrop-blur sm:px-5">
          <SidebarTrigger
            aria-label="Mở hoặc thu gọn thanh điều hướng"
            title="Mở hoặc thu gọn thanh điều hướng"
          />
          <span aria-hidden="true" className="h-5 w-px bg-border" />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">
              <Suspense fallback="Không gian làm việc">
                <RouteLabel />
              </Suspense>
            </p>
            <p className="hidden truncate text-xs text-muted-foreground sm:block">
              RAG Workspace
            </p>
          </div>
        </header>
        <div className="flex min-h-0 flex-1 flex-col bg-muted/30 p-4 sm:p-6 lg:p-8">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
