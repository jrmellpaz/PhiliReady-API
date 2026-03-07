# PhiliReady — Frontend Implementation Plan
## Aligned with Backend API v2.0.0

**Stack:** TanStack Start v1 RC · React · TypeScript · TanStack Query v5 · React-Leaflet v4 · Recharts · Tailwind CSS  
**Map Level:** All Philippine cities/municipalities (not Cebu-only)  
**Deployment:** Vercel  
**Communicates with:** FastAPI backend at `/api/v1` (deployed on Railway/Render)  
**API Convention:** All JSON response keys are **camelCase**. Request bodies accept both camelCase and snake_case.

---

## Table of Contents

1. [Project Setup](#project-setup)
2. [Must-Have #1 — Choropleth Map](#must-have-1--choropleth-map)
3. [Must-Have #2 — Detail Side Panel](#must-have-2--detail-side-panel)
4. [Must-Have #3 — Forecast Chart](#must-have-3--forecast-chart)
5. [Must-Have #4 — Disaster Simulator](#must-have-4--disaster-simulator)
6. [Must-Have #5 — Custom City Simulator](#must-have-5--custom-city-simulator)
7. [Must-Have #6 — Dashboard Page](#must-have-6--dashboard-page)
8. [Must-Have #7 — Authentication](#must-have-7--authentication)
9. [Must-Have #8 — Admin Panel](#must-have-8--admin-panel)
10. [Must-Have #9 — Prices Management](#must-have-9--prices-management)
11. [Must-Have #10 — Weather Widget](#must-have-10--weather-widget)
12. [Deployment — Vercel](#deployment--vercel)
13. [Testing Checklist Before Demo](#testing-checklist-before-demo)

---

## Project Setup

### 1. Initialize TanStack Start

```bash
npm create @tanstack/router@latest philiready-frontend
cd philiready-frontend
```

When prompted:
- Framework: **TanStack Start**
- Language: **TypeScript**
- Styling: **Tailwind CSS**

### 2. Install Dependencies

```bash
# Map
npm install leaflet react-leaflet
npm install -D @types/leaflet

# Charts
npm install recharts

# UI primitives
npm install @radix-ui/react-slider @radix-ui/react-tabs @radix-ui/react-select

# Utilities
npm install clsx date-fns zod

# Fonts (via Google Fonts — add to root HTML or use next/font equivalent)
```

### 3. Environment Variables

Create `.env` at project root:

```env
VITE_API_BASE_URL=https://your-backend.railway.app/api/v1
```

> **Important:** The backend serves all routes under `/api/v1`. Include that prefix in the base URL.

Access in code via `import.meta.env.VITE_API_BASE_URL`.

### 4. Folder Structure

```
app/
├── routes/
│   ├── __root.tsx              # Root layout, global CSS imports
│   ├── index.tsx               # Dashboard (map + forecast)
│   ├── simulate.tsx            # Disaster scenario simulator
│   ├── simulator.tsx           # Custom city simulator
│   ├── login.tsx               # Login page
│   ├── admin.tsx               # Admin panel (users + city access)
│   └── prices.tsx              # Prices management (admin)
├── components/
│   ├── map/
│   │   ├── MapWrapper.tsx      # SSR-safe lazy wrapper
│   │   ├── CebuMap.tsx         # Core Leaflet component (client-only)
│   │   └── DetailPanel.tsx     # Right-side panel on city click
│   ├── forecast/
│   │   └── ForecastChart.tsx
│   ├── simulator/
│   │   └── SimulatorControls.tsx
│   ├── weather/
│   │   └── WeatherStrip.tsx    # 7-day weather bar
│   └── ui/
│       ├── StatBar.tsx
│       └── Navbar.tsx
├── lib/
│   ├── api.ts                  # All fetch functions
│   ├── queries.ts              # TanStack Query hooks
│   ├── types.ts                # Zod schemas + inferred TS types
│   ├── auth.ts                 # JWT token helpers
│   ├── colors.ts               # Color scale utilities
│   └── leaflet-fix.ts          # Marker icon patch
└── styles/
    └── globals.css             # Tailwind directives + Leaflet CSS import
```

---

## Must-Have #1 — Choropleth Map

### Overview

Renders cities/municipalities as colored polygons on a dark Leaflet map. Color encodes demand intensity. Clicking a polygon loads the Detail Panel.

### Step 1 — Download GeoJSON Locally

```bash
mkdir -p public/geo
# Download the national Philippine municipalities GeoJSON
curl -o public/geo/municities.json \
  "https://raw.githubusercontent.com/faeldon/philippines-json-maps/master/2023/geojson/municities/lowres/municities.0.001.json"
```

> **Note:** The backend has been aligned to use official 10-digit PSGC codes natively. The GeoJSON's `adm3_psgc` keys will map perfectly to the API's returned keys.

Store locally in `public/geo/` — never fetch from GitHub at runtime.

### Step 2 — Fix Leaflet CSS + Marker Icons

```css
/* app/styles/globals.css */
@import 'leaflet/dist/leaflet.css';
@tailwind base;
@tailwind components;
@tailwind utilities;
```

```ts
// app/lib/leaflet-fix.ts
import L from 'leaflet'
import icon from 'leaflet/dist/images/marker-icon.png'
import icon2x from 'leaflet/dist/images/marker-icon-2x.png'
import shadow from 'leaflet/dist/images/marker-shadow.png'

delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({ iconUrl: icon, iconRetinaUrl: icon2x, shadowUrl: shadow })
```

### Step 3 — SSR-Safe Wrapper

TanStack Start runs SSR. Leaflet accesses `window` on import and will crash the server render. This wrapper prevents that.

```tsx
// app/components/map/MapWrapper.tsx
import { Suspense, lazy } from 'react'

const CebuMap = lazy(() => import('./CebuMap'))

export function MapWrapper(props: React.ComponentProps<typeof CebuMap>) {
  return (
    <div style={{ height: '100%', width: '100%' }}>
      <Suspense fallback={<MapSkeleton />}>
        {typeof window !== 'undefined' && <CebuMap {...props} />}
      </Suspense>
    </div>
  )
}

function MapSkeleton() {
  return (
    <div className="h-full w-full bg-[#0F2040] flex items-center
                    justify-center text-[#6B7F99] font-mono text-sm">
      Initializing map...
    </div>
  )
}
```

Also add to `vite.config.ts`:

```ts
export default defineConfig({
  plugins: [tanstackStart(), react()],
  ssr: {
    noExternal: ['leaflet', 'react-leaflet'],
  },
})
```

### Step 4 — Define Shared Types

All types match the backend's camelCase JSON responses exactly.

```ts
// app/lib/types.ts
import { z } from 'zod'

// ── Hazard types ──────────────────────────────────────────────────────────
export type HazardType = 'typhoon' | 'flood' | 'earthquake' | 'volcanic'

// ── Map Heatmap ───────────────────────────────────────────────────────────
// GET /map/demand-heat → { "1380600000": 0.92, ... }
export const DemandScoreMapSchema = z.record(z.string(), z.number())
export type DemandScoreMap = z.infer<typeof DemandScoreMapSchema>

// ── Forecast ──────────────────────────────────────────────────────────────
// GET /forecast/{pcode} → ForecastPoint[]
// Per-item confidence intervals + cost fields (all camelCase from API)
export const ForecastPointSchema = z.object({
  day:        z.string(),       // "Mar 07"
  rice:       z.number(),       // kg
  riceLower:  z.number(),       // rice confidence lower bound
  riceUpper:  z.number(),       // rice confidence upper bound
  riceCost:   z.number(),       // estimated rice cost (PHP)
  water:      z.number(),       // liters
  waterLower: z.number(),
  waterUpper: z.number(),
  waterCost:  z.number(),
  meds:       z.number(),       // medicine kit units
  medsLower:  z.number(),
  medsUpper:  z.number(),
  medsCost:   z.number(),
  kits:       z.number(),       // hygiene kit units
  kitsLower:  z.number(),
  kitsUpper:  z.number(),
  kitsCost:   z.number(),
  totalCost:  z.number(),       // sum of all item costs for the day (PHP)
})
export type ForecastPoint = z.infer<typeof ForecastPointSchema>

// ── City Detail ───────────────────────────────────────────────────────────
// GET /cities/{pcode} → CityDetail
export const CityDemandSchema = z.object({
  rice:  z.number(),
  water: z.number(),
  meds:  z.number(),
  kits:  z.number(),
})

export const CityDetailSchema = z.object({
  pcode:      z.string(),
  name:       z.string(),
  province:   z.string(),
  region:     z.string(),
  population: z.number(),
  households: z.number(),
  riskScore:  z.number(),         // camelCase (was risk_score)
  zoneType:   z.string(),         // "coastal" | "inland"
  demand:     CityDemandSchema,
  updatedBy:  z.string().nullable(),
  updatedAt:  z.string().nullable(),
})
export type CityDetail = z.infer<typeof CityDetailSchema>

// ── Auth ──────────────────────────────────────────────────────────────────
// POST /auth/login → TokenResponse
export const TokenResponseSchema = z.object({
  accessToken: z.string(),
  tokenType:   z.string(),
})
export type TokenResponse = z.infer<typeof TokenResponseSchema>

// GET /auth/me → UserProfile
export const UserProfileSchema = z.object({
  id:       z.number(),
  email:    z.string(),
  fullName: z.string(),
  role:     z.string(),   // "admin" | "lgu"
})
export type UserProfile = z.infer<typeof UserProfileSchema>

// ── Admin ─────────────────────────────────────────────────────────────────
// GET /admin/users → UserWithCities[]
export const UserWithCitiesSchema = z.object({
  id:       z.number(),
  email:    z.string(),
  fullName: z.string(),
  role:     z.string(),
  cities:   z.array(z.string()),
})
export type UserWithCities = z.infer<typeof UserWithCitiesSchema>

// ── Prices ────────────────────────────────────────────────────────────────
// GET /prices → PriceItem[]
export const PriceItemSchema = z.object({
  itemKey:      z.string(),     // "rice_kg" | "water_liters" | "meds_units" | "kits_units"
  label:        z.string(),     // "Rice"
  unit:         z.string(),     // "kg"
  pricePerUnit: z.number(),     // PHP
  updatedAt:    z.string(),
})
export type PriceItem = z.infer<typeof PriceItemSchema>

// ── Weather ───────────────────────────────────────────────────────────────
// GET /weather → WeatherDay[]
export const WeatherDaySchema = z.object({
  date:     z.string(),     // "2026-03-07"
  precipMm: z.number(),     // total precipitation mm
  windKmh:  z.number(),     // max wind speed km/h
  alert:    z.boolean(),    // true if precip > 30mm
})
export type WeatherDay = z.infer<typeof WeatherDaySchema>

// ── City Update ───────────────────────────────────────────────────────────
// PATCH /cities/{pcode} → CityUpdateResult
export const CityUpdateResultSchema = z.object({
  message:      z.string(),
  changes:      z.record(z.unknown()),
  newRiskScore: z.number(),
  updatedBy:    z.string(),
  updatedAt:    z.string(),
})
export type CityUpdateResult = z.infer<typeof CityUpdateResultSchema>

// ── Simulation Request ────────────────────────────────────────────────────
// POST /simulate body
export interface SimulationPayload {
  hazardType: HazardType
  severity: number
}
```

### Step 5 — Auth Helpers

```ts
// app/lib/auth.ts
const TOKEN_KEY = 'philiready_token'

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}
```

### Step 6 — API Functions

```ts
// app/lib/api.ts
import { authHeaders } from './auth'
import type {
  HazardType, DemandScoreMap, CityDetail, ForecastPoint,
  TokenResponse, UserProfile, UserWithCities, PriceItem,
  WeatherDay, CityUpdateResult, SimulationPayload,
} from './types'

const BASE = import.meta.env.VITE_API_BASE_URL  // includes /api/v1

async function get<T>(path: string, auth = false): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: auth ? authHeaders() : {},
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

async function mutate<T>(
  method: string, path: string, body?: unknown, auth = false
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(auth ? authHeaders() : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

// ── Map ───────────────────────────────────────────────────────────────────
export function fetchDemandHeatmap(
  hazard?: HazardType, severity?: number
): Promise<DemandScoreMap> {
  const params = new URLSearchParams()
  if (hazard) params.set('hazard_type', hazard)
  if (severity) params.set('severity', String(severity))
  const qs = params.toString()
  return get(`/map/demand-heat${qs ? `?${qs}` : ''}`)
}

// ── Cities ────────────────────────────────────────────────────────────────
export function fetchCityDetail(pcode: string): Promise<CityDetail> {
  return get(`/cities/${pcode}`)
}

export function updateCity(
  pcode: string,
  body: Record<string, unknown>
): Promise<CityUpdateResult> {
  return mutate('PATCH', `/cities/${pcode}`, body, true)
}

// ── Forecast ──────────────────────────────────────────────────────────────
export function fetchForecast(
  pcode: string, hazard?: HazardType, severity?: number
): Promise<ForecastPoint[]> {
  const params = new URLSearchParams()
  if (hazard) params.set('hazard_type', hazard)
  if (severity) params.set('severity', String(severity))
  const qs = params.toString()
  return get(`/forecast/${pcode}${qs ? `?${qs}` : ''}`)
}

// ── Simulate (global heatmap recalc) ──────────────────────────────────────
export function runSimulation(
  payload: SimulationPayload
): Promise<DemandScoreMap> {
  return mutate('POST', '/simulate', payload)
}

// ── Simulator (custom city — query params, no DB) ─────────────────────────
export function fetchCustomCityForecast(params: {
  population: number
  households?: number
  is_coastal?: number
  poverty_pct?: float
  flood_zone?: string
  eq_zone?: string
  hazard_type?: string
  severity?: number
}): Promise<ForecastPoint[]> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined) qs.set(k, String(v))
  })
  return get(`/simulator/forecast?${qs}`)
}

// ── Auth ──────────────────────────────────────────────────────────────────
export function login(
  email: string, password: string
): Promise<TokenResponse> {
  return mutate('POST', '/auth/login', { email, password })
}

export function register(body: {
  email: string; password: string; fullName: string; role?: string
}): Promise<UserProfile> {
  return mutate('POST', '/auth/register', body, true)
}

export function fetchMe(): Promise<UserProfile> {
  return get('/auth/me', true)
}

// ── Admin ─────────────────────────────────────────────────────────────────
export function fetchUsers(): Promise<UserWithCities[]> {
  return get('/admin/users', true)
}

export function assignCities(
  userId: number, pcodes: string[]
): Promise<{ message: string; added: string[]; skipped: string[]; invalid: string[] }> {
  return mutate('POST', `/admin/users/${userId}/cities`, { pcodes }, true)
}

export function removeCityAccess(
  userId: number, pcode: string
): Promise<{ message: string }> {
  return mutate('DELETE', `/admin/users/${userId}/cities/${pcode}`, undefined, true)
}

// ── Prices ────────────────────────────────────────────────────────────────
export function fetchPrices(): Promise<PriceItem[]> {
  return get('/prices')
}

export function updatePrice(
  itemKey: string, pricePerUnit: number
): Promise<PriceItem> {
  return mutate('PATCH', `/prices/${itemKey}`, { pricePerUnit }, true)
}

// ── Weather ───────────────────────────────────────────────────────────────
export function fetchWeather(): Promise<WeatherDay[]> {
  return get('/weather')
}
```

### Step 7 — TanStack Query Hooks

```ts
// app/lib/queries.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchDemandHeatmap, fetchCityDetail, fetchForecast, runSimulation,
  fetchCustomCityForecast, fetchMe, fetchUsers, fetchPrices, fetchWeather,
  updateCity, updatePrice, assignCities, removeCityAccess,
} from './api'
import type { HazardType } from './types'

// ── Map ───────────────────────────────────────────────────────────────────
export function useDemandHeatmap(hazard?: HazardType, severity?: number) {
  return useQuery({
    queryKey: ['demand-heatmap', hazard, severity],
    queryFn: () => fetchDemandHeatmap(hazard, severity),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
}

// ── City Detail ───────────────────────────────────────────────────────────
export function useCityDetail(pcode: string | null) {
  return useQuery({
    queryKey: ['city-detail', pcode],
    queryFn: () => fetchCityDetail(pcode!),
    enabled: !!pcode,
  })
}

// ── Forecast ──────────────────────────────────────────────────────────────
export function useForecast(
  pcode: string | null, hazard?: HazardType, severity?: number
) {
  return useQuery({
    queryKey: ['forecast', pcode, hazard, severity],
    queryFn: () => fetchForecast(pcode!, hazard, severity),
    enabled: !!pcode,
  })
}

// ── Simulation (global) ──────────────────────────────────────────────────
export function useSimulation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: runSimulation,
    onSuccess: (data) => {
      qc.setQueryData(['demand-heatmap', undefined, undefined], data)
    },
  })
}

// ── Custom City Simulator ─────────────────────────────────────────────────
export function useCustomCityForecast(params: Parameters<typeof fetchCustomCityForecast>[0] | null) {
  return useQuery({
    queryKey: ['custom-city-forecast', params],
    queryFn: () => fetchCustomCityForecast(params!),
    enabled: !!params && !!params.population,
  })
}

// ── Auth ──────────────────────────────────────────────────────────────────
export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: fetchMe,
    retry: false,
    staleTime: 5 * 60_000,
  })
}

// ── Admin ─────────────────────────────────────────────────────────────────
export function useUsers() {
  return useQuery({
    queryKey: ['admin-users'],
    queryFn: fetchUsers,
  })
}

export function useAssignCities() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, pcodes }: { userId: number; pcodes: string[] }) =>
      assignCities(userId, pcodes),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  })
}

export function useRemoveCityAccess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, pcode }: { userId: number; pcode: string }) =>
      removeCityAccess(userId, pcode),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  })
}

// ── Prices ────────────────────────────────────────────────────────────────
export function usePrices() {
  return useQuery({
    queryKey: ['prices'],
    queryFn: fetchPrices,
    staleTime: 60_000,
  })
}

export function useUpdatePrice() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ itemKey, price }: { itemKey: string; price: number }) =>
      updatePrice(itemKey, price),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prices'] })
      // Costs in forecasts depend on prices — invalidate forecasts too
      qc.invalidateQueries({ queryKey: ['forecast'] })
    },
  })
}

// ── City Update ───────────────────────────────────────────────────────────
export function useUpdateCity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ pcode, body }: { pcode: string; body: Record<string, unknown> }) =>
      updateCity(pcode, body),
    onSuccess: (_data, { pcode }) => {
      qc.invalidateQueries({ queryKey: ['city-detail', pcode] })
      qc.invalidateQueries({ queryKey: ['demand-heatmap'] })
    },
  })
}

// ── Weather ───────────────────────────────────────────────────────────────
export function useWeather() {
  return useQuery({
    queryKey: ['weather'],
    queryFn: fetchWeather,
    staleTime: 60 * 60_000,  // 1 hour — data cached daily on backend
  })
}
```

### Step 8 — Color Scale Utility

```ts
// app/lib/colors.ts
export function getDemandColor(score: number): string {
  if (score > 0.8) return '#E94560'  // critical
  if (score > 0.6) return '#F5A623'  // high
  if (score > 0.4) return '#FFD166'  // moderate
  if (score > 0.2) return '#4A9EFF'  // low
  return '#16C79A'                   // minimal
}

export function getRiskLabel(score: number): string {
  if (score > 0.8) return 'CRITICAL'
  if (score > 0.6) return 'HIGH'
  if (score > 0.4) return 'MODERATE'
  if (score > 0.2) return 'LOW'
  return 'MINIMAL'
}
```

### Step 9 — CebuMap Component

```tsx
// app/components/map/CebuMap.tsx
// ⚠️  This file is CLIENT-ONLY. Never import it directly — use MapWrapper.
import { MapContainer, TileLayer, GeoJSON } from 'react-leaflet'
import type { Feature, GeoJsonObject } from 'geojson'
import type { Layer, PathOptions } from 'leaflet'
import { getDemandColor } from '../../lib/colors'
import { useDemandHeatmap } from '../../lib/queries'
import type { HazardType } from '../../lib/types'
import '../../lib/leaflet-fix'

interface Props {
  onCitySelect: (pcode: string, name: string) => void
  selectedPcode: string | null
  simHazard?: HazardType
  simSeverity?: number
  simActive: boolean
}

export default function CebuMap({
  onCitySelect, selectedPcode, simHazard, simSeverity, simActive,
}: Props) {
  const { data: scores, isLoading } = useDemandHeatmap(
    simActive ? simHazard : undefined,
    simActive ? simSeverity : undefined
  )

  function featureStyle(feature?: Feature): PathOptions {
    const pcode = feature?.properties?.ADM3_PCODE ?? ''
    const score = scores?.[pcode] ?? 0.1
    const isSelected = pcode === selectedPcode
    return {
      fillColor: getDemandColor(score),
      fillOpacity: isSelected ? 0.95 : 0.7,
      color: isSelected ? '#ffffff' : '#1E3A5F',
      weight: isSelected ? 2.5 : 1.2,
      opacity: 1,
    }
  }

  function onEachFeature(feature: Feature, layer: Layer) {
    const props = feature.properties ?? {}
    const pcode = props.ADM3_PCODE ?? ''
    const name = props.ADM3_EN ?? 'Unknown'
    const score = scores?.[pcode] ?? 0

    layer.bindTooltip(
      `<div style="font-family:monospace;font-size:12px;padding:2px 4px">
        <strong>${name}</strong><br/>
        Demand Score: ${(score * 100).toFixed(0)}%
      </div>`,
      { sticky: true }
    )

    // @ts-ignore
    layer.on({
      mouseover(e: any) {
        e.target.setStyle({ fillOpacity: 0.9, weight: 2, color: '#aaaaaa' })
        e.target.bringToFront()
      },
      mouseout(e: any) { e.target.setStyle(featureStyle(feature)) },
      click() { onCitySelect(pcode, name) },
    })
  }

  return (
    <MapContainer
      center={[12.8797, 121.7740]}  // Philippines center
      zoom={6}
      style={{ height: '100%', width: '100%' }}
      zoomControl={true}
      attributionControl={false}
    >
      <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
      {!isLoading && scores && (
        <GeoJSON
          key={JSON.stringify(scores)}
          data={'/geo/municities.json' as unknown as GeoJsonObject}
          style={featureStyle}
          onEachFeature={onEachFeature}
        />
      )}
    </MapContainer>
  )
}
```

> **Note on GeoJSON data prop:** React-Leaflet accepts a URL string for the `data` prop in v4. If this causes issues, fetch the JSON in a `useEffect` and pass the parsed object instead.

---

## Must-Have #2 — Detail Side Panel

### Overview

Slides in when a city/municipality is clicked. Shows the city's full demographics, peak demand breakdown, cost estimates, and the 7-day forecast chart.

**Key differences from old plan:**
- City detail now includes `province`, `region`, `households`, `updatedBy`, `updatedAt`
- Uses `riskScore` (camelCase) not `risk_score`
- Forecast data includes per-item cost fields — display cost summary
- `zoneType` is `"coastal"` or `"inland"` (camelCase)

```tsx
// app/components/map/DetailPanel.tsx
import { useCityDetail, useForecast } from '../../lib/queries'
import { ForecastChart } from '../forecast/ForecastChart'
import { getDemandColor, getRiskLabel } from '../../lib/colors'
import type { HazardType } from '../../lib/types'

interface Props {
  pcode: string
  name: string
  onClose: () => void
  hazard?: HazardType
  severity?: number
  simActive: boolean
}

const ITEMS = [
  { key: 'rice',  label: 'Rice',         unit: 'kg',    color: '#4A9EFF' },
  { key: 'water', label: 'Water',        unit: 'L',     color: '#16C79A' },
  { key: 'meds',  label: 'Med Kits',     unit: 'units', color: '#F5A623' },
  { key: 'kits',  label: 'Hygiene Kits', unit: 'units', color: '#E94560' },
] as const

export function DetailPanel({ pcode, name, onClose,
                              hazard, severity, simActive }: Props) {
  const { data: city, isLoading: cityLoading } = useCityDetail(pcode)
  const { data: forecast, isLoading: fxLoading } = useForecast(
    pcode, simActive ? hazard : undefined, simActive ? severity : undefined
  )

  if (cityLoading) return <PanelShell name={name} onClose={onClose}><Spinner /></PanelShell>

  // Calculate total 7-day cost from forecast data
  const totalWeekCost = forecast?.reduce((sum, d) => sum + d.totalCost, 0) ?? 0

  return (
    <PanelShell name={name} onClose={onClose}>
      {/* Location + Risk badge */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[9px] text-[#6B7F99] font-mono">
          {city?.province} · {city?.region}
        </span>
      </div>
      <div className="flex items-center gap-2 mb-4">
        <span style={{
          background: getDemandColor(city?.riskScore ?? 0) + '22',
          color: getDemandColor(city?.riskScore ?? 0),
          border: `1px solid ${getDemandColor(city?.riskScore ?? 0)}44`,
          padding: '2px 8px', borderRadius: 3,
          fontSize: 11, fontFamily: 'monospace',
        }}>
          {getRiskLabel(city?.riskScore ?? 0)}
        </span>
        <span style={{
          background: '#132848', border: '1px solid #1E3A5F',
          padding: '2px 8px', borderRadius: 3,
          fontSize: 11, fontFamily: 'monospace', color: '#6B7F99',
        }}>
          {city?.zoneType?.toUpperCase()}
        </span>
        {simActive && (
          <span style={{
            background: '#E9456022', color: '#E94560',
            border: '1px solid #E9456044',
            padding: '2px 8px', borderRadius: 3,
            fontSize: 11, fontFamily: 'monospace',
          }}>
            SIM ACTIVE
          </span>
        )}
      </div>

      {/* Stats grid — now includes households */}
      <div className="grid grid-cols-2 gap-2 mb-4">
        <Stat label="Population" value={city?.population.toLocaleString() ?? '—'} />
        <Stat label="Households" value={city?.households.toLocaleString() ?? '—'} />
        <Stat label="Risk Score"
              value={`${((city?.riskScore ?? 0) * 100).toFixed(0)}%`}
              color={getDemandColor(city?.riskScore ?? 0)} />
        <Stat label="7-Day Cost"
              value={`₱${(totalWeekCost / 1000).toFixed(0)}K`}
              color="#F5A623" />
      </div>

      {/* Demand bars */}
      <div className="mb-4">
        <p className="text-[10px] text-[#6B7F99] font-mono mb-2 tracking-widest">
          PEAK DEMAND ESTIMATE
        </p>
        {ITEMS.map(({ key, label, unit, color }) => {
          const val = city?.demand[key as keyof typeof city.demand] ?? 0
          const max = 20000
          return (
            <div key={key} className="mb-2">
              <div className="flex justify-between mb-1">
                <span className="text-[10px] font-mono text-[#E8EDF4]">{label}</span>
                <span className="text-[10px] font-mono" style={{ color }}>
                  {val.toLocaleString()} {unit}
                </span>
              </div>
              <div className="h-[3px] bg-[#1E3A5F] rounded-full overflow-hidden">
                <div style={{
                  width: `${Math.min((val / max) * 100, 100)}%`,
                  background: color, height: '100%',
                  transition: 'width 0.4s ease',
                }} />
              </div>
            </div>
          )
        })}
      </div>

      {/* Forecast chart */}
      <p className="text-[10px] text-[#6B7F99] font-mono mb-2 tracking-widest">
        7-DAY FORECAST
      </p>
      {fxLoading
        ? <Spinner />
        : forecast && <ForecastChart data={forecast} />
      }

      {/* Audit trail */}
      {city?.updatedBy && (
        <p className="text-[8px] text-[#6B7F99] font-mono mt-3">
          Last edited by {city.updatedBy}
          {city.updatedAt && ` · ${new Date(city.updatedAt).toLocaleDateString()}`}
        </p>
      )}
    </PanelShell>
  )
}

function PanelShell({ name, onClose, children }: {
  name: string; onClose: () => void; children: React.ReactNode
}) {
  return (
    <div style={{
      width: 280, background: '#0F2040',
      border: '1px solid #1E3A5F', borderRadius: 10,
      padding: 16, display: 'flex', flexDirection: 'column',
      overflowY: 'auto', flexShrink: 0,
    }}>
      <div className="flex justify-between items-start mb-1">
        <h2 className="text-sm font-semibold text-[#E8EDF4] leading-tight">{name}</h2>
        <button onClick={onClose}
          className="text-[#6B7F99] hover:text-[#E8EDF4] text-base leading-none ml-2">
          ✕
        </button>
      </div>
      {children}
    </div>
  )
}

function Stat({ label, value, color = '#E8EDF4' }: {
  label: string; value: string; color?: string
}) {
  return (
    <div style={{
      background: '#132848', border: '1px solid #1E3A5F',
      borderRadius: 6, padding: '8px 10px',
    }}>
      <p className="text-[9px] text-[#6B7F99] font-mono mb-1 tracking-widest uppercase">{label}</p>
      <p className="text-base font-mono font-medium" style={{ color }}>{value}</p>
    </div>
  )
}

function Spinner() {
  return (
    <div className="flex items-center justify-center h-16 text-[#6B7F99] text-xs font-mono">
      loading...
    </div>
  )
}
```

---

## Must-Have #3 — Forecast Chart

Updated to show per-item confidence intervals and daily cost in tooltip.

```tsx
// app/components/forecast/ForecastChart.tsx
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import type { ForecastPoint } from '../../lib/types'

const SERIES = [
  { key: 'rice',  label: 'Rice (kg)',   color: '#4A9EFF' },
  { key: 'water', label: 'Water (L)',   color: '#16C79A' },
  { key: 'meds',  label: 'Med Kits',    color: '#F5A623' },
  { key: 'kits',  label: 'Hygiene',     color: '#E94560' },
] as const

const TOOLTIP_STYLE = {
  contentStyle: {
    background: '#132848', border: '1px solid #1E3A5F',
    borderRadius: 6, fontSize: 10, fontFamily: 'monospace',
  },
  labelStyle: { color: '#E8EDF4' },
}

// Custom tooltip to show cost alongside demand
function ForecastTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const data = payload[0]?.payload as ForecastPoint
  return (
    <div style={{
      ...TOOLTIP_STYLE.contentStyle, padding: '8px 10px', color: '#E8EDF4',
    }}>
      <p style={{ marginBottom: 4, fontWeight: 600 }}>{label}</p>
      {SERIES.map(({ key, label: l, color }) => (
        <p key={key} style={{ color, margin: '2px 0' }}>
          {l}: {data[key as keyof ForecastPoint]?.toLocaleString()}
          <span style={{ color: '#6B7F99', marginLeft: 6 }}>
            ₱{(data[`${key}Cost` as keyof ForecastPoint] as number / 1000).toFixed(0)}K
          </span>
        </p>
      ))}
      <p style={{ color: '#F5A623', marginTop: 4, borderTop: '1px solid #1E3A5F', paddingTop: 4 }}>
        Total: ₱{(data.totalCost / 1000).toFixed(0)}K
      </p>
    </div>
  )
}

export function ForecastChart({ data }: { data: ForecastPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
        <defs>
          {SERIES.map(({ key, color }) => (
            <linearGradient key={key} id={`grad-${key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0}   />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1E3A5F" vertical={false} />
        <XAxis dataKey="day"
          tick={{ fontSize: 9, fill: '#6B7F99', fontFamily: 'monospace' }}
          tickLine={false} />
        <YAxis
          tick={{ fontSize: 9, fill: '#6B7F99', fontFamily: 'monospace' }}
          tickLine={false} axisLine={false} />
        <Tooltip content={<ForecastTooltip />} />
        <Legend wrapperStyle={{ fontSize: 9, fontFamily: 'monospace' }} />
        {SERIES.map(({ key, label, color }) => (
          <Area key={key}
            type="monotone" dataKey={key} name={label}
            stroke={color} strokeWidth={2}
            fill={`url(#grad-${key})`} dot={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}
```

---

## Must-Have #4 — Disaster Simulator

Same concept as before — select hazard + severity, activate to re-render the global map.

Uses `POST /simulate` (returns heatmap scores) and `GET /forecast/{pcode}?hazard_type=X&severity=Y` for preview.

> See `app/routes/simulate.tsx` — same structure as the original plan. Key change: the preview pcode should use a valid PSGC from the seeded database (check your seed data for available pcodes).

---

## Must-Have #5 — Custom City Simulator

### Overview

**NEW** — A page at `/simulator` that lets users build a hypothetical city and see what the forecast would look like. Uses `GET /simulator/forecast` with all params as query strings (bookmarkable/shareable URLs).

```tsx
// app/routes/simulator.tsx (conceptual)
// Uses fetchCustomCityForecast() with these query params:
//   population, households, is_coastal, poverty_pct,
//   flood_zone, eq_zone, hazard_type, severity
//
// The URL state IS the simulation state:
//   /simulator?population=500000&severity=3&is_coastal=1&flood_zone=high
//
// Store all slider/input values in URL search params via TanStack Router.
// Response is the same ForecastPoint[] shape as GET /forecast/{pcode}.
```

---

## Must-Have #6 — Dashboard Page

Same layout as before. Key updates:
- Uses `/api/v1` prefix (included in `VITE_API_BASE_URL`)
- Weather strip added to the stat bar
- Navbar includes login/logout state
- City count should come from the heatmap data (`Object.keys(scores).length`) instead of hardcoded

---

## Must-Have #7 — Authentication

### Overview

Login page at `/login`. JWT stored in `localStorage`. Token sent via `Authorization: Bearer <token>` header on protected requests.

**Endpoints used:**
- `POST /auth/login` — returns `{ accessToken, tokenType }`
- `GET /auth/me` — returns `{ id, email, fullName, role }`
- `POST /auth/register` — admin-only, creates new user

**Key notes:**
- Token expires after 24 hours (configurable on backend)
- The `role` field is `"admin"` or `"lgu"`
- City editing (`PATCH /cities/{pcode}`) requires auth + city access
- Admin endpoints require `role === "admin"`

---

## Must-Have #8 — Admin Panel

### Overview

Page at `/admin` (admin-only). Manage users and their city access.

**Endpoints used:**
- `GET /admin/users` — list all users with assigned cities
- `POST /admin/users/{id}/cities` — assign city pcodes (idempotent)
- `DELETE /admin/users/{id}/cities/{pcode}` — remove city access
- `POST /auth/register` — create new user (admin-only)

---

## Must-Have #9 — Prices Management

### Overview

Page or section at `/prices` (admin-only for editing, public for viewing). Shows current relief goods unit prices.

**Endpoints used:**
- `GET /prices` — list all prices (public)
- `PATCH /prices/{item_key}` — update a price (admin-only)

**Valid `item_key` values:** `rice_kg`, `water_liters`, `meds_units`, `kits_units`

**Note:** Prices affect the cost fields in forecast responses. After updating a price, invalidate forecast query cache.

---

## Must-Have #10 — Weather Widget

### Overview

A compact strip or card showing the 7-day weather forecast.

**Endpoint:** `GET /weather` — returns 7 `WeatherDay` objects.

**Fields:** `date` (ISO), `precipMm`, `windKmh`, `alert` (boolean — true if precip > 30mm)

Data is cached daily on the backend (one Open-Meteo API call per day). Set `staleTime` to 1 hour.

---

## Deployment — Vercel

### 1. Configure Build

```json
// package.json
{
  "scripts": {
    "dev":   "vinxi dev",
    "build": "vinxi build",
    "start": "vinxi start"
  }
}
```

### 2. Environment Variable on Vercel

In Vercel dashboard → Settings → Environment Variables:

```
VITE_API_BASE_URL = https://your-backend.railway.app/api/v1
```

### 3. Deploy

```bash
npm install -g vercel
vercel --prod
```

Vercel auto-detects TanStack Start / Vinxi builds. No additional config needed.

### 4. CORS Note

The FastAPI backend already allows requests from:
- `https://philiready.vercel.app` (production)
- `http://localhost:3000` (Next.js default)
- `http://localhost:5173` (Vite default)

If your Vercel domain differs, update the backend `allow_origins` list.

---

## Testing Checklist Before Demo

### Map & Core
- [ ] GeoJSON loads and all cities render with demand-based colors
- [ ] Clicking a city opens the Detail Panel with correct name, province, and PSGC
- [ ] Detail panel shows population, households, risk score, zone type, peak demand
- [ ] Forecast chart renders 7 data points with all 4 item lines
- [ ] Forecast tooltip shows per-item costs and daily total cost

### Simulation
- [ ] `/simulate` page: selecting typhoon severity 3 → clicking Activate → redirects to `/` with map re-colored
- [ ] Sim active badge appears in navbar
- [ ] Clicking ✕ on sim badge clears simulation, map returns to baseline
- [ ] `/simulator` page: custom city form with sliders → forecast preview updates

### Authentication
- [ ] Login page works with `admin@philiready.ph` / `admin123`
- [ ] Token stored in localStorage after login
- [ ] `GET /auth/me` returns correct user profile
- [ ] Protected endpoints fail gracefully with 401 when token expired
- [ ] Logout clears token

### Admin
- [ ] Admin can see all users at `/admin`
- [ ] Admin can assign/remove city access
- [ ] Admin can register new users

### Prices & Weather
- [ ] Prices page displays all 4 items with current PHP prices
- [ ] Admin can update a price
- [ ] Weather widget shows 7-day forecast with alert indicators

### Infrastructure
- [ ] All API calls go to `VITE_API_BASE_URL` (no localhost calls in production)
- [ ] No `window is not defined` errors in build logs
- [ ] Map tiles load (CartoDB dark tiles — no API key needed)
- [ ] All JSON keys received are camelCase (check Network tab)
