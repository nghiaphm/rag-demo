"use client"

import { Badge } from "@/components/ui/badge"
import { summarizeDepartmentShares } from "@/lib/hr/analytics"
import type { DepartmentHeadcount } from "@/types/hr"

export function DepartmentChart({
  departments,
}: {
  departments: readonly DepartmentHeadcount[]
}) {
  const shares = summarizeDepartmentShares(departments)
  const totalOpenRoles = departments.reduce((sum, item) => sum + item.openRoles, 0)

  return (
    <section
      aria-labelledby="dept-chart-title"
      className="flex h-full flex-col justify-between rounded-xl border bg-card p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 pb-5">
        <div>
          <h2 id="dept-chart-title" className="text-base font-semibold tracking-tight">
            Nhân sự theo phòng ban
          </h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Cơ cấu nhân sự hiện hữu và nhu cầu tuyển dụng (Dữ liệu mô phỏng HR).
          </p>
        </div>
        <Badge variant="secondary" className="tabular-nums">
          {totalOpenRoles} vị trí đang mở
        </Badge>
      </div>

      <ul className="space-y-2.5" aria-label="Biểu đồ số lượng nhân viên theo phòng ban">
        {shares.map((item) => (
          <li
            key={item.id}
            className="rounded-lg px-2.5 py-2 transition-colors hover:bg-muted/45"
          >
            <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2 text-sm">
              <span className="font-medium text-foreground">{item.department}</span>
              <span className="flex items-center gap-2 text-xs tabular-nums text-muted-foreground">
                {item.openRoles > 0 && (
                  <span className="rounded bg-accent px-1.5 py-0.5 text-[11px] font-medium text-accent-foreground">
                    +{item.openRoles} tuyển mới
                  </span>
                )}
                <span>
                  <strong className="font-semibold text-foreground">{item.count}</strong> nhân sự ({item.sharePercent}%)
                </span>
              </span>
            </div>
            <div
              role="progressbar"
              aria-label={`${item.department}: ${item.count} nhân sự`}
              aria-valuenow={item.count}
              aria-valuemin={0}
              aria-valuemax={shares[0]?.count ?? 100}
              className="h-2 w-full overflow-hidden rounded-full bg-muted"
            >
              <div
                className="h-full rounded-full bg-[var(--chart-1)] transition-all duration-300"
                style={{ width: `${item.barWidthPercent}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
