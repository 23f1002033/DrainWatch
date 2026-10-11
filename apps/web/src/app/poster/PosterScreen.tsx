"use client";

import { useSearchParams } from "next/navigation";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { Button, ErrorBox, Spinner } from "@/components/ui";
import { TENANT_PATTERN } from "@/lib/report";

export function PosterScreen() {
  const tenant = useSearchParams().get("t") ?? "";
  const valid = TENANT_PATTERN.test(tenant);
  const [url, setUrl] = useState("");
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!valid) return;
    const target = `${window.location.origin}/report/?t=${encodeURIComponent(tenant)}`;
    setUrl(target);
    QRCode.toString(target, { type: "svg", errorCorrectionLevel: "M", margin: 0, color: { dark: "#000000", light: "#ffffff" } })
      .then(setSvg)
      .catch(() => setFailed(true));
  }, [tenant, valid]);

  if (!valid) {
    return (
      <main className="mx-auto max-w-lg px-4 py-10">
        <ErrorBox message="Missing or invalid campus code. Open this page as /poster/?t=your-campus." />
      </main>
    );
  }

  return (
    <>
      <style>{`@page { size: A4 portrait; margin: 0; }`}</style>
      <div className="no-print mx-auto flex max-w-[210mm] items-center justify-between gap-3 px-4 py-3">
        <p className="text-sm text-slate-600">A4 poster for {tenant}. Print at 100% scale.</p>
        <Button variant="primary" onClick={() => window.print()} disabled={!svg} title={svg ? undefined : "QR code not ready"}>
          Print
        </Button>
      </div>
      <main className="mx-auto flex h-[297mm] w-[210mm] flex-col items-center border border-slate-200 bg-white px-[18mm] py-[20mm] text-center text-slate-900 print:border-0">
        <p className="text-[14pt] font-semibold uppercase tracking-[0.2em] text-slate-500">Facility team</p>
        <h1 className="mt-[8mm] text-[40pt] leading-tight font-bold">Waterlogging or a blocked drain?</h1>
        <p className="mt-[6mm] text-[18pt] text-slate-700">Scan to report it. No app or account needed.</p>
        <div className="mt-[14mm] flex h-[110mm] w-[110mm] items-center justify-center">
          {failed ? (
            <ErrorBox message="Could not generate the QR code." />
          ) : svg ? (
            <div className="h-full w-full [&>svg]:h-full [&>svg]:w-full" role="img" aria-label={`QR code linking to ${url}`} dangerouslySetInnerHTML={{ __html: svg }} />
          ) : (
            <Spinner label="Generating QR code" />
          )}
        </div>
        <p className="mt-[10mm] font-mono text-[11pt] break-all text-slate-600">{url}</p>
        <ul className="mt-auto space-y-[2mm] text-left text-[13pt] text-slate-700">
          <li>1. Choose waterlogging or blocked drain.</li>
          <li>2. Say where it is, or share your location.</li>
          <li>3. Keep the reference code you get back.</li>
        </ul>
        <p className="mt-[8mm] text-[10pt] text-slate-500">If water is near electrical equipment, keep away from it.</p>
      </main>
    </>
  );
}
