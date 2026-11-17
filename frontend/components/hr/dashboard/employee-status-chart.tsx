"use client"

import { summarizeContractStatuses } from "@/lib/hr/analytics"
import type { ContractStatusMetric } from "@/types/hr"

const TONE_TOKENS: Record<ContractStatusMetric["tone"], { stroke: string; dot: string }> = {
  primary: {
    stroke: "stroke-[var(--chart-1)]",
    dot: "bg-[var(--chart-1)]",
  },
  info: {
    stroke: "stroke-[var(--chart-2)]",
    dot: "bg-[var(--chart-2)]",
  },
  warning: {
    stroke: "stroke-[var(--chart-3)]",
    dot: "bg-[var(--chart-3)]",
  },
  muted: {
    stroke: "stroke-[var(--chart-4)]",
    dot: "bg-[var(--chart-4)]",
  },
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
    <section
      aria-labelledby="contract-chart-title"
      className="flex h-full flex-col justify-between rounded-xl border bg-card p-6"
    >
      <div className="pb-5">
        <h2 id="contract-chart-title" className="text-base font-semibold tracking-tight">
          Trạng thái nhân viên &amp; hợp đồng
        </h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Phân loại hợp đồng lao động trên tổng {total} nhân sự (Dữ liệu mô phỏng HR).
        </p>
      </div>

      <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
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
              strokeWidth="15"
              className="stroke-muted"
            />
            {segments.map((segment) => (
              <circle
                key={segment.id}
                cx="70"
                cy="70"
                r={radius}
                fill="none"
                strokeWidth="15"
                strokeDasharray={`${segment.dashLength} ${circumference}`}
                strokeDashoffset={segment.dashOffset}
                className={TONE_TOKENS[segment.tone].stroke}
              />
            ))}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className="text-2xl font-semibold tabular-nums tracking-tight">{total}</span>
            <span className="text-[11px] text-muted-foreground">nhân sự</span>
          </div>
        </div>

        <ul className="w-full flex-1 divide-y divide-border" aria-label="Chi tiết trạng thái hợp đồng">
          {shares.map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between gap-3 py-2.5 text-sm first:pt-0 last:pb-0"
            >
              <span className="flex min-w-0 items-center gap-2.5">
                <span
                  aria-hidden="true"
                  className={`size-2.5 shrink-0 rounded-full ${TONE_TOKENS[item.tone].dot}`}
                />
                <span className="truncate text-foreground">{item.label}</span>
              </span>
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                <strong className="font-semibold text-foreground">{item.count}</strong> ({item.sharePercent}%)
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
