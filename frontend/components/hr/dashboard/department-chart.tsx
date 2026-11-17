"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Nhân sự theo phòng ban</CardTitle>
        <CardDescription>
          Phân bổ nhân sự hiện tại và {totalOpenRoles} vị trí đang mở tuyển (Dữ liệu mô phỏng HR).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-4" aria-label="Biểu đồ số lượng nhân viên theo phòng ban">
          {shares.map((item) => (
            <li key={item.id} className="space-y-1.5">
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                <span className="font-medium">{item.department}</span>
                <span className="text-xs text-muted-foreground">
                  <strong className="font-semibold text-foreground">{item.count}</strong> nhân sự ({item.sharePercent}%)
                  {item.openRoles > 0 && ` · ${item.openRoles} đang tuyển`}
                </span>
              </div>
              <div
                role="progressbar"
                aria-label={`${item.department}: ${item.count} nhân sự`}
                aria-valuenow={item.count}
                aria-valuemin={0}
                aria-valuemax={shares[0]?.count ?? 100}
                className="h-2.5 w-full overflow-hidden rounded-full bg-muted"
              >
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${item.barWidthPercent}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
