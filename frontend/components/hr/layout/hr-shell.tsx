"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Suspense, type ReactNode } from "react"
import {
  ArrowLeft,
  BookOpen,
  Building2,
  Compass,
  Files,
  LayoutDashboard,
  MessageSquareText,
} from "lucide-react"

import { ServiceHealth } from "@/components/layout/service-health"
import { HrChatbotWidget } from "@/components/hr/chatbot/hr-chatbot-widget"
import { HrHeaderUser } from "@/components/hr/layout/hr-header-user"
import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
import { HrTourOverlay } from "@/components/hr/tour/hr-tour-overlay"
import { useOptionalHrTour } from "@/components/hr/tour/hr-tour-provider"
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
  useSidebar,
} from "@/components/ui/sidebar"
import {
  ALLOWED_HR_ROUTES,
  HR_ROUTE_MANIFEST,
  matchesHrRoute,
} from "@/lib/hr/page-context"
import type { HrPageRoute, HrUserProfile } from "@/types/hr"

export { matchesHrRoute }

const HR_ROUTE_ICONS: Record<HrPageRoute, typeof LayoutDashboard> = {
  "/hr": LayoutDashboard,
  "/hr/documents": Files,
  "/hr/guide": BookOpen,
}

export const hrNavigationItems: readonly {
  href: HrPageRoute
  label: string
  icon: typeof LayoutDashboard
  exact?: boolean
}[] = Object.freeze(
  ALLOWED_HR_ROUTES.map((route) => {
    const meta = HR_ROUTE_MANIFEST[route]
    return {
      href: meta.route,
      label: meta.navLabel,
      icon: HR_ROUTE_ICONS[route],
      ...(meta.exact ? { exact: true } : {}),
    }
  }),
)

function HrNavigationLinks({ pathname }: { pathname?: string }) {
  const { isMobile, setOpenMobile } = useSidebar()

  return (
    <nav aria-label="Điều hướng HR Portal">
      <SidebarGroup>
        <SidebarGroupLabel>Cổng nhân sự</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            {hrNavigationItems.map((item) => {
              const isActive = pathname
                ? matchesHrRoute(pathname, item.href, item.exact)
                : false
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

function HrNavigation() {
  const pathname = usePathname()
  return <HrNavigationLinks pathname={pathname} />
}

function HrSidebar({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  const { isMobile, setOpenMobile } = useSidebar()
  const { openWidget } = useHrChatbot()
  const tour = useOptionalHrTour()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-3.5">
        <Link
          href="/hr"
          className="flex min-h-10 items-center gap-3 rounded-lg px-2 outline-none ring-sidebar-ring transition-colors hover:bg-sidebar-accent focus-visible:ring-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
          onClick={() => {
            if (isMobile) setOpenMobile(false)
          }}
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground shadow-2xs">
            <Building2 className="size-4" aria-hidden="true" />
          </span>
          <span className="min-w-0 leading-tight group-data-[collapsible=icon]:hidden">
            <span className="block truncate text-sm font-semibold tracking-tight">HR Portal</span>
            <span className="block truncate text-xs text-sidebar-foreground/70">
              Nhân sự và tri thức
            </span>
          </span>
        </Link>
      </SidebarHeader>
      <SidebarSeparator />
      <SidebarContent className="px-1 py-2">
        <Suspense fallback={<HrNavigationLinks />}>
          <HrNavigation />
        </Suspense>
        <SidebarSeparator className="my-2" />
        <SidebarGroup>
          <SidebarGroupLabel>Công cụ liên kết</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  type="button"
                  tooltip="Mở Trợ lý HR"
                  onClick={() => {
                    if (isMobile) setOpenMobile(false)
                    openWidget()
                  }}
                >
                  <MessageSquareText aria-hidden="true" />
                  <span>Trợ lý chính sách HR</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  type="button"
                  tooltip="Bắt đầu Product Tour"
                  onClick={() => {
                    if (isMobile) setOpenMobile(false)
                    tour?.startTour(0, "all")
                  }}
                >
                  <Compass aria-hidden="true" />
                  <span>Product Tour</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Về RAG Workspace"
                  render={
                    <Link
                      href="/chat"
                      onClick={() => {
                        if (isMobile) setOpenMobile(false)
                      }}
                    />
                  }
                >
                  <ArrowLeft aria-hidden="true" />
                  <span>Về RAG Workspace</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="space-y-2.5 p-3.5">
        <div className="group-data-[collapsible=icon]:hidden">
          <ServiceHealth apiBaseUrl={apiBaseUrl} />
        </div>
        <p className="px-2 text-[11px] leading-5 text-sidebar-foreground/65 group-data-[collapsible=icon]:hidden">
          Không gian hỏi đáp chính nằm tại /chat.
        </p>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}

export function HrShell({
  children,
  apiBaseUrl,
  user,
  chatbotSlot,
}: {
  children: ReactNode
  apiBaseUrl: string | null
  user?: HrUserProfile
  chatbotSlot?: ReactNode
}) {
  return (
    <SidebarProvider>
      <HrSidebar apiBaseUrl={apiBaseUrl} />
      <SidebarInset id="main-content" tabIndex={-1} className="min-h-svh min-w-0">
        <HrHeaderUser user={user} />
        <div className="flex min-h-0 flex-1 flex-col bg-muted/30 p-4 sm:p-6 lg:p-8">
          {children}
        </div>
        {chatbotSlot ?? <HrChatbotWidget apiBaseUrl={apiBaseUrl} />}
        <Suspense fallback={null}>
          <HrTourOverlay />
        </Suspense>
      </SidebarInset>
    </SidebarProvider>
  )
}
