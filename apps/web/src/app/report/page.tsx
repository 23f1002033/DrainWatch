import { Suspense } from "react";
import { ReportScreen } from "./ReportScreen";

export const metadata = { title: "Report a drain problem - DrainWatch" };

export default function ReportPage() {
  return (
    <Suspense>
      <ReportScreen />
    </Suspense>
  );
}
