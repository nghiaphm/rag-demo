"use client"

import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { HrKpiCard } from "@/types/hr"

function TrendPill({ card }: { card: HrKpiCard }) {
  const Icon =
    card.trend === "up"
      ? ArrowUpRight
      : card.trend === "down"
        ? ArrowDownRight
        : Minus

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium",
        card.trend === "neutral"
          ? "bg-muted text-muted-foreground"
          : "bg-accent text-accent-foreground"
      )}
    >
      <Icon className="size-3.5 text-primary" aria-hidden="true" />
      <span>{card.deltaLabel}</span>
    </span>
  )
}

export function HrKpiCards({
  kpis,
  asOfLabel,
}: {
  kpis: readonly HrKpiCard[]
  asOfLabel: string
}) {
  return (
    <section aria-labelledby="hr-kpi-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="hr-kpi-heading" className="text-base font-semibold tracking-tight">
          Chỉ số nhân sự tổng quan
        </h2>
        <Badge variant="outline" className="bg-card text-xs font-normal text-muted-foreground">
          {asOfLabel}
        </Badge>
      </div>

      <div className="grid divide-y divide-border overflow-hidden rounded-xl border bg-card sm:grid-cols-2 sm:divide-x lg:grid-cols-4 lg:divide-y-0">
        {kpis.map((card) => (
          <div
            key={card.id}
            className="flex flex-col justify-between gap-3 px-6 py-5 transition-colors hover:bg-muted/30"
          >
            <p className="text-xs font-medium text-muted-foreground">
              {card.label}
            </p>
            <div className="space-y-2">
              <p className="text-3xl font-semibold tracking-tight tabular-nums text-foreground">
                {card.value}
              </p>
              <TrendPill card={card} />
            </div>
            <p className="text-xs leading-5 text-muted-foreground">
              {card.helperText}
            </p>
          </div>
        ))}
      </div>
    </section>
  )
}
