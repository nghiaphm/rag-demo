"use client"

import { ArrowDownRight, ArrowUpRight, Minus, Users } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { HrKpiCard } from "@/types/hr"

function TrendBadge({ card }: { card: HrKpiCard }) {
  const Icon =
    card.trend === "up"
      ? ArrowUpRight
      : card.trend === "down"
        ? ArrowDownRight
        : Minus

  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground">
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
        <div className="flex items-center gap-2">
          <Users className="size-4 text-primary" aria-hidden="true" />
          <h2 id="hr-kpi-heading" className="text-base font-semibold">
            Chỉ số nhân sự tổng quan
          </h2>
        </div>
        <Badge variant="outline" className="text-xs font-normal">
          {asOfLabel}
        </Badge>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((card) => (
          <Card key={card.id} className="gap-3 py-4">
            <CardHeader className="pb-0">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.label}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              <p className="text-2xl font-semibold tracking-tight">{card.value}</p>
              <TrendBadge card={card} />
              <p className="text-xs leading-5 text-muted-foreground">{card.helperText}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  )
}
