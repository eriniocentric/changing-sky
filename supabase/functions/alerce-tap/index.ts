// Changing Sky relay to the ALeRCE TAP service (https://tap.alerce.online).
// ALeRCE's TAP server sends no CORS headers, so a web page cannot call it directly. This function
// accepts ONLY a sky position, a radius (<= 1 deg) and a time range (<= 31 days), builds the ADQL
// itself (no free-form queries), runs the detection and classification queries in parallel and
// returns both as CSV text with CORS headers for the Changing Sky site.
// Deployed 2026-11-19 in project lnfxxsxmkecwedheyvuq under the function name "clever-api" (Supabase fixes the name at first deploy);
// the page uses RELAY_FN in pipeline/make_explore.py. To redeploy: same function, paste this file.
// Deploy: Supabase dashboard -> Edge Functions -> new function "alerce-tap" -> paste this file ->
// turn OFF "Verify JWT" (the site's publishable key is not a JWT) -> Deploy.
const TAP = "https://tap.alerce.online/tap/sync";
const ALLOWED = ["https://eriniocentric.github.io", "http://localhost:8000", "http://127.0.0.1:8000"];
const MAXREC = 20000;

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": ALLOWED.includes(origin) ? origin : ALLOWED[0],
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Vary": "Origin",
  };
}
function cone(ra, dec, r) { return `1=CONTAINS(POINT('ICRS',o.ra,o.dec),CIRCLE('ICRS',${ra},${dec},${r}))`; }
function queries(ra, dec, r, a, b) {
  const det = `SELECT d.oid, d.measurement_id, d.mjd, d.ra, d.dec, d.band, l.psfflux, l.psffluxerr, l.snr, l.reliability,
 l.isdipole, l.pixelflags_saturatedcenter, l.glint_trail, l.traillength, o.firstdiasourcemjdtai, o.ndiasources
FROM alerce_tap.lsst_dia_object AS o JOIN alerce_tap.detection AS d ON d.oid=o.oid
JOIN alerce_tap.lsst_detection AS l ON l.measurement_id=d.measurement_id AND l.oid=d.oid
WHERE ${cone(ra, dec, r)} AND d.mjd BETWEEN ${a} AND ${b}`;
  // classifiers 3 = stamp_classifier_rubin_beta_20260421 (current, from May 2026) and 1 = stamp_classifier_rubin_beta (earlier); the page prefers 3.
  // Objects are selected by having a detection in the window: lsst_dia_object's first/last dates proved unreliable.
  const cls = `SELECT DISTINCT p.oid, p.classifier_id, t.class_name, p.probability FROM alerce_tap.lsst_dia_object AS o
JOIN alerce_tap.detection AS d ON d.oid=o.oid JOIN alerce_tap.probability AS p ON p.oid=o.oid
JOIN alerce_tap.taxonomy AS t ON t.class_id=p.class_id AND t.classifier_id=p.classifier_id
WHERE ${cone(ra, dec, r)} AND p.ranking=1 AND p.classifier_id IN (1,3) AND d.mjd BETWEEN ${a} AND ${b}`;
  return [det, cls];
}
async function runTap(q) {
  const res = await fetch(TAP, { method: "POST", body: new URLSearchParams({ REQUEST: "doQuery", LANG: "ADQL", FORMAT: "csv", MAXREC: String(MAXREC), QUERY: q }) });
  const text = await res.text();
  if (!res.ok || text.startsWith("<")) throw new Error("ALeRCE TAP " + res.status + (text.startsWith("<") ? " (query error)" : ""));
  return text;
}
export async function handle(req) {
  const h = corsHeaders(req.headers.get("origin") || "");
  if (req.method === "OPTIONS") return new Response("ok", { headers: h });
  const json = (obj, status = 200, extra = {}) => new Response(JSON.stringify(obj), { status, headers: { ...h, "Content-Type": "application/json", ...extra } });
  let p = {};
  try { p = req.method === "POST" ? await req.json() : Object.fromEntries(new URL(req.url).searchParams); } catch (_) { return json({ error: "bad request body" }, 400); }
  const ra = Number(p.ra), dec = Number(p.dec), r = Number(p.radius), a = Number(p.mjd_min), b = Number(p.mjd_max);
  const ok = [ra, dec, r, a, b].every(Number.isFinite) && ra >= 0 && ra < 360 && dec >= -90 && dec <= 90 && r > 0 && r <= 1 && b > a && b - a <= 31 && a > 60000;
  if (!ok) return json({ error: "need ra [0,360), dec [-90,90], 0 < radius <= 1 deg, mjd_min < mjd_max, range <= 31 days" }, 400);
  const t0 = Date.now();
  try {
    const [q1, q2] = queries(ra.toFixed(6), dec.toFixed(6), r.toFixed(6), a.toFixed(6), b.toFixed(6));
    const [detections, classes] = await Promise.all([runTap(q1), runTap(q2)]);
    const n = detections.split("\n").filter((l) => l.trim()).length - 1;
    return json({ source: "ALeRCE TAP via Changing Sky relay", ra, dec, radius: r, mjd_min: a, mjd_max: b, n_detections: n, truncated: n >= MAXREC, seconds: (Date.now() - t0) / 1000, detections, classes },
      200, { "Cache-Control": "public, max-age=600" });
  } catch (e) { return json({ error: String(e && e.message || e) }, 502); }
}
if (typeof Deno !== "undefined") Deno.serve(handle);
