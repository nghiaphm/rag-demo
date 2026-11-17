"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { summarizeContractStatuses } from "@/lib/hr/analytics"
import type { ContractStatusMetric } from "@/types/hr"

const TONE_COLORS: Record<ContractStatusMetric["tone"], { stroke: string; dot: string }> = {
  primary: { stroke: "stroke-primary", dot: "bg-primary" },
  info: { stroke: "stroke-chart-2", dot: "bg-chart-2" },
  warning: { stroke: "stroke-chart-4", dot: "bg-chart-4" },
  muted: { stroke: "stroke-muted-foreground/60", dot: "bg-muted-foreground/60" },
}

export function EmployeeStatusChart({
  statuses,
}: {
  statuses: readonly ContractStatusMetric[]
}) {
  const shares = summarizeContractStatuses(statuses)
  const total = statuses.reduce((sum, item) => sum + item.count, 0)
  const radius = 52
  const circumference = 2 * Math.PI * radius
  const segments = shares.reduce<
    Array<(typeof shares)[number] & { dashLength: number; dashOffset: number; endPercent: number }>
  >((acc, item) => {
    const startPercent = acc.length > 0 ? acc[acc.length - 1].endPercent : 0
    const dashLength = (item.sharePercent / 100) * circumference
    const dashOffset = -(startPercent / 100) * circumference
    acc.push({
      ...item,
      dashLength,
      dashOffset,
      endPercent: startPercent + item.sharePercent,
    })
    return acc
  }, [])

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Trạng thái nhân viên &amp; hợp đồng</CardTitle>
        <CardDescription>
          Cơ cấu hợp đồng lao động trên tổng {total} nhân sự (Dữ liệu mô phỏng HR).
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-6 sm:flex-row sm:items-start">
        <div className="relative flex size-36 shrink-0 items-center justify-center">
          <svg
            viewBox="0 0 140 140"
            className="size-full -rotate-90"
            role="img"
            aria-label={`Biểu đồ trạng thái hợp đồng trên ${total} nhân sự`}
          >
            <circle
              cx="70"
              cy="70"
              r={radius}
              fill="none"
              strokeWidth="16"
              className="stroke-muted"
            />
            {segments.map((segment) => (
              <circle
                key={segment.id}
                cx="70"
                cy="70"
                r={radius}
                fill="none"
                strokeWidth="16"
                strokeDasharray={`${segment.dashLength} ${circumference}`}
                strokeDashoffset={segment.dashOffset}
                className={TONE_COLORS[segment.tone].stroke}
              />
            ))}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className="text-xl font-semibold">{total}</span>
            <span className="text-[11px] text-muted-foreground">nhân sự</span>
          </div>
        </div>

        <ul className="w-full flex-1 space-y-3" aria-label="Chi tiết trạng thái hợp đồng">
          {shares.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="flex min-w-0 items-center gap-2">
                <span
                  aria-hidden="true"
                  className={`size-2.5 shrink-0 rounded-full ${TONE_COLORS[item.tone].dot}`}
                />
                <span className="truncate">{item.label}</span>
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">
                <strong className="font-semibold text-foreground">{item.count}</strong> ({item.sharePercent}%)
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
