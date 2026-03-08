# PhiliReady API Reference

> **Base URL:** `http://localhost:8000/api/v1`
> **Version:** 2.0.0
> **Swagger Docs:** `http://localhost:8000/docs`

All JSON response keys are **camelCase**. The API also accepts both **camelCase** and **snake_case** in request bodies.

---

## Table of Contents

1. [Authentication](#1-authentication)
   - [POST /auth/login](#post-authlogin)
   - [POST /auth/register](#post-authregister)
   - [GET /auth/me](#get-authme)
2. [Cities](#2-cities)
   - [GET /cities/{pcode}](#get-citiespcode)
   - [PATCH /cities/{pcode}](#patch-citiespcode)
3. [Forecast](#3-forecast)
   - [GET /forecast/{pcode}](#get-forecastpcode)
4. [Map](#4-map)
   - [GET /map/demand-heat](#get-mapdemand-heat)
5. [Simulate](#5-simulate)
   - [POST /simulate](#post-simulate)
6. [Simulator (Custom City)](#6-simulator-custom-city)
   - [GET /simulator/forecast](#get-simulatorforecast)
7. [Prices](#7-prices)
   - [GET /prices](#get-prices)
   - [PATCH /prices/{item_key}](#patch-pricesitem_key)
8. [Admin](#8-admin)
   - [GET /admin/users](#get-adminusers)
   - [POST /admin/users/{id}/cities](#post-adminusersidcities)
   - [DELETE /admin/users/{id}/cities/{pcode}](#delete-adminusersidcitiespcode)
9. [Weather](#9-weather)
   - [GET /weather](#get-weather)
10. [Health Check](#10-health-check)
    - [GET /health](#get-health)

---

## Authentication Header

Protected endpoints require a JWT token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

| Icon | Meaning |
|------|---------|
| PUBLIC | No authentication required |
| AUTH | Any logged-in user |
| ADMIN | Requires `admin` role |
| CITY ACCESS | Requires city-level permission |

---

## 1. Authentication

### POST /auth/login

**PUBLIC** — Authenticate and receive a JWT access token.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | `string` | Yes | User's email address |
| `password` | `string` | Yes | Plain-text password |

**Example Request:**
```json
{
  "email": "admin@philiready.ph",
  "password": "admin123"
}
```

**Response `200 OK`:**

| Field | Type | Description |
|-------|------|-------------|
| `accessToken` | `string` | JWT access token (valid for 24 hours by default) |
| `tokenType` | `string` | Always `"bearer"` |

**Example Response:**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
  "tokenType": "bearer"
}
```

**Error Responses:**

| Status | Detail |
|--------|--------|
| `401` | Invalid email or password |

---

### POST /auth/register

**ADMIN** — Create a new user account.

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `email` | `string` | Yes | — | User's email address |
| `password` | `string` | Yes | — | Plain-text password (hashed on server) |
| `fullName` | `string` | Yes | — | Display name |
| `role` | `string` | No | `"lgu"` | `"admin"` or `"lgu"` |

**Example Request:**
```json
{
  "email": "lgu_cebu@philiready.ph",
  "password": "securepassword123",
  "fullName": "Cebu DRRMO Officer",
  "role": "lgu"
}
```

**Response `201 Created`:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | User ID |
| `email` | `string` | Email address |
| `fullName` | `string` | Display name |
| `role` | `string` | `"admin"` or `"lgu"` |

**Example Response:**
```json
{
  "id": 2,
  "email": "lgu_cebu@philiready.ph",
  "fullName": "Cebu DRRMO Officer",
  "role": "lgu"
}
```

**Error Responses:**

| Status | Detail |
|--------|--------|
| `401` | Missing or invalid token |
| `403` | User is not an admin |
| `409` | Email already registered |

---

### GET /auth/me

**AUTH** — Get the currently authenticated user's profile.

**Headers:** `Authorization: Bearer <token>`

**Response `200 OK`:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | User ID |
| `email` | `string` | Email address |
| `fullName` | `string` | Display name |
| `role` | `string` | `"admin"` or `"lgu"` |

**Example Response:**
```json
{
  "id": 1,
  "email": "admin@philiready.ph",
  "fullName": "System Admin",
  "role": "admin"
}
```

**Error Responses:**

| Status | Detail |
|--------|--------|
| `401` | Missing, invalid, or expired token |

---

## 2. Cities

### GET /cities/{pcode}

**PUBLIC** — Get detailed demographics, risk, and peak demand for a single city.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pcode` | `string` | Yes | City PSGC code, e.g. `1380600000` |

**Response `200 OK`:**

| Field | Type | Description |
|-------|------|-------------|
| `pcode` | `string` | PSGC code |
| `name` | `string` | City/municipality name |
| `province` | `string` | Province |
| `region` | `string` | Region |
| `population` | `integer` | Total population (2024 Census) |
| `households` | `integer` | Number of households |
| `povertyPct` | `float` | Poverty incidence (0.0-1.0) |
| `isCoastal` | `integer` | `0` = inland, `1` = coastal |
| `floodZone` | `string` | `"low"`, `"medium"`, or `"high"` |
| `eqZone` | `string` | `"low"`, `"medium"`, or `"high"` |
| `riskScore` | `float` | Composite risk score (0.0-1.0) |
| `zoneType` | `string` | `"coastal"` or `"inland"` |
| `demand` | `object` | Peak single-day demand (see below) |
| `updatedBy` | `string\|null` | Email of last editor |
| `updatedAt` | `string\|null` | ISO timestamp of last edit |

**`demand` object:**

| Field | Type | Description |
|-------|------|-------------|
| `rice` | `float` | Peak daily rice demand (kg) |
| `water` | `float` | Peak daily water demand (liters) |
| `meds` | `float` | Peak daily medicine kits demand (units) |
| `kits` | `float` | Peak daily hygiene kits demand (units) |

**Example Response:**
```json
{
  "pcode": "1380600000",
  "name": "Caloocan City",
  "province": "Metro Manila",
  "region": "NCR",
  "population": 1750000,
  "households": 417791,
  "povertyPct": 0.20,
  "isCoastal": 0,
  "floodZone": "medium",
  "eqZone": "medium",
  "riskScore": 0.4223,
  "zoneType": "inland",
  "demand": {
    "rice": 87735.6,
    "water": 877356.0,
    "meds": 4679.2,
    "kits": 4094.3
  },
  "updatedBy": "admin@philiready.ph",
  "updatedAt": "2026-03-07T04:59:50.722048"
}
```

**Error Responses:**

| Status | Detail |
|--------|--------|
| `404` | City with the given PSGC code not found |

---

### PATCH /cities/{pcode}

**AUTH + CITY ACCESS** — Edit a city's parameters. Admins can edit any city. LGU users can only edit their assigned cities.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pcode` | `string` | Yes | City PSGC code |

**Request Body** (all fields optional -- only provided fields are updated):

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `population` | `integer` | No | >= 1 | Total population |
| `households` | `integer` | No | >= 1 | Number of households |
| `povertyPct` | `float` | No | 0.0-1.0 | Poverty incidence |
| `isCoastal` | `integer` | No | 0 or 1 | Coastal classification |
| `floodZone` | `string` | No | `"low"` `"medium"` `"high"` | Flood zone |
| `eqZone` | `string` | No | `"low"` `"medium"` `"high"` | Earthquake zone |

> **Note:** The `riskScore` is automatically recomputed after any edit.

**Example Request:**
```json
{
  "population": 1750000,
  "floodZone": "high"
}
```

**Response `200 OK`:**

| Field | Type | Description |
|-------|------|-------------|
| `message` | `string` | Success message |
| `pcode` | `string` | PSGC code |
| `name` | `string` | City/municipality name |
| `province` | `string` | Province |
| `region` | `string` | Region |
| `population` | `integer` | Total population |
| `households` | `integer` | Number of households |
| `povertyPct` | `float` | Poverty incidence (0.0-1.0) |
| `isCoastal` | `integer` | `0` = inland, `1` = coastal |
| `floodZone` | `string` | `"low"`, `"medium"`, or `"high"` |
| `eqZone` | `string` | `"low"`, `"medium"`, or `"high"` |
| `riskScore` | `float` | Recomputed risk score (0.0-1.0) |
| `zoneType` | `string` | `"coastal"` or `"inland"` |
| `updatedBy` | `string` | Email of the editor |
| `updatedAt` | `string` | ISO timestamp |

**Example Response:**
```json
{
  "message": "Updated city 'Caloocan City' (1380600000)",
  "pcode": "1380600000",
  "name": "Caloocan City",
  "province": "Metro Manila",
  "region": "NCR",
  "population": 1750000,
  "households": 417791,
  "povertyPct": 0.20,
  "isCoastal": 0,
  "floodZone": "high",
  "eqZone": "medium",
  "riskScore": 0.5223,
  "zoneType": "inland",
  "updatedBy": "admin@philiready.ph",
  "updatedAt": "2026-03-07T05:00:00.000000"
}
```

**Error Responses:**

| Status | Detail |
|--------|--------|
| `400` | No fields to update / validation error |
| `401` | Missing or invalid token |
| `403` | User does not have access to this city |
| `404` | City not found |

---

## 3. Forecast

### GET /forecast/{pcode}

**PUBLIC** — Get a 7-day relief demand forecast for a specific city.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pcode` | `string` | Yes | City PSGC code |

**Query Parameters:**

| Parameter | Type | Required | Default | Constraints | Description |
|-----------|------|----------|---------|-------------|-------------|
| `hazard_type` | `string` | No | `null` | `typhoon` `flood` `earthquake` `volcanic` | Hazard type to simulate |
| `severity` | `integer` | No | `null` | 1-4 | Severity level (1=minor, 4=catastrophic) |

> Without query params, returns baseline demand using the city's risk score.
> With both `hazard_type` and `severity`, returns simulated scenario demand.

**Example Request:**
```
GET /api/v1/forecast/1380600000?hazard_type=typhoon&severity=3
```

**Response `200 OK`:** Array of 7 `ForecastPoint` objects.

| Field | Type | Description |
|-------|------|-------------|
| `day` | `string` | Date label, e.g. `"Mar 07"` |
| `rice` | `float` | Predicted rice demand (kg) |
| `riceLower` | `float` | Rice demand lower bound (-20%) |
| `riceUpper` | `float` | Rice demand upper bound (+20%) |
| `riceCost` | `float` | Estimated rice cost (PHP) |
| `water` | `float` | Predicted water demand (liters) |
| `waterLower` | `float` | Water demand lower bound |
| `waterUpper` | `float` | Water demand upper bound |
| `waterCost` | `float` | Estimated water cost (PHP) |
| `meds` | `float` | Predicted medicine kits demand (units) |
| `medsLower` | `float` | Medicine kits lower bound |
| `medsUpper` | `float` | Medicine kits upper bound |
| `medsCost` | `float` | Estimated medicine cost (PHP) |
| `kits` | `float` | Predicted hygiene kits demand (units) |
| `kitsLower` | `float` | Hygiene kits lower bound |
| `kitsUpper` | `float` | Hygiene kits upper bound |
| `kitsCost` | `float` | Estimated hygiene kits cost (PHP) |
| `totalCost` | `float` | Total estimated cost for the day (PHP) |

**Example Response:**
```json
[
  {
    "day": "Mar 07",
    "rice": 12600.0,
    "riceLower": 10080.0,
    "riceUpper": 15120.0,
    "riceCost": 630000.0,
    "water": 126000.0,
    "waterLower": 100800.0,
    "waterUpper": 151200.0,
    "waterCost": 1890000.0,
    "meds": 672.0,
    "medsLower": 537.6,
    "medsUpper": 806.4,
    "medsCost": 336000.0,
    "kits": 588.0,
    "kitsLower": 470.4,
    "kitsUpper": 705.6,
    "kitsCost": 205800.0,
    "totalCost": 3061800.0
  }
]
```

**Error Responses:**

| Status | Detail |
|--------|--------|
| `404` | City not found |

---

## 4. Map

### GET /map/demand-heat

**PUBLIC** — Get normalized demand scores for all cities (for choropleth heatmap).

**Query Parameters:**

| Parameter | Type | Required | Default | Constraints | Description |
|-----------|------|----------|---------|-------------|-------------|
| `hazard_type` | `string` | No | `null` | `typhoon` `flood` `earthquake` `volcanic` | Hazard type for simulation |
| `severity` | `integer` | No | `null` | 1-4 | Severity level |

> Without params: returns baseline risk scores for all cities.
> With params: returns simulated demand scores (0.0-1.0) for all cities.

**Example Request:**
```
GET /api/v1/map/demand-heat?hazard_type=typhoon&severity=3
```

**Response `200 OK`:** Object with pcode keys and normalized scores (0.0-1.0).

```json
{
  "1380600000": 0.92,
  "102801000": 0.71,
  "102802000": 0.45
}
```

---

## 5. Simulate

### POST /simulate

**PUBLIC** — Recalculate all demand scores under a simulated disaster scenario.

**Request Body:**

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `hazardType` | `string` | Yes | `typhoon` `flood` `earthquake` `volcanic` | Type of disaster |
| `severity` | `integer` | Yes | 1-4 | 1=minor, 2=moderate, 3=major, 4=catastrophic |

**Example Request:**
```json
{
  "hazardType": "typhoon",
  "severity": 3
}
```

**Response `200 OK`:** Same shape as `GET /map/demand-heat`.

```json
{
  "1380600000": 0.97,
  "102801000": 0.89
}
```

---

## 6. Simulator (Custom City)

### GET /simulator/forecast

**PUBLIC** — Generate a 7-day forecast for a hypothetical custom city. No database interaction -- purely computational. Parameters are designed to be stored as URL query params for persistence across page refreshes.

**Query Parameters:**

| Parameter | Type | Required | Default | Constraints | Description |
|-----------|------|----------|---------|-------------|-------------|
| `population` | `integer` | Yes | — | >= 1 | Total population |
| `households` | `integer` | No | `pop / 4.1` | >= 1 | Number of households |
| `is_coastal` | `integer` | No | `0` | 0 or 1 | Coastal classification |
| `poverty_pct` | `float` | No | `0.20` | 0.0-1.0 | Poverty incidence |
| `flood_zone` | `string` | No | `"medium"` | `low` `medium` `high` | Flood zone |
| `eq_zone` | `string` | No | `"medium"` | `low` `medium` `high` | Earthquake zone |
| `hazard_type` | `string` | No | `"typhoon"` | `typhoon` `flood` `earthquake` `volcanic` | Simulated hazard |
| `severity` | `integer` | No | `2` | 1-4 | Severity level |

**Example Request:**
```
GET /api/v1/simulator/forecast?population=500000&severity=3&is_coastal=1&flood_zone=high
```

**Response `200 OK`:** Array of 7 `ForecastPoint` objects (same shape as `GET /forecast/{pcode}`).

```json
[
  {
    "day": "Mar 07",
    "rice": 12600.0,
    "riceLower": 10080.0,
    "riceUpper": 15120.0,
    "riceCost": 630000.0,
    "water": 126000.0,
    "waterLower": 100800.0,
    "waterUpper": 151200.0,
    "waterCost": 1890000.0,
    "meds": 672.0,
    "medsLower": 537.6,
    "medsUpper": 806.4,
    "medsCost": 336000.0,
    "kits": 588.0,
    "kitsLower": 470.4,
    "kitsUpper": 705.6,
    "kitsCost": 205800.0,
    "totalCost": 3061800.0
  }
]
```

---

## 7. Prices

### GET /prices

**PUBLIC** — List all current relief goods unit prices.

**Response `200 OK`:** Array of `PriceResponse` objects.

| Field | Type | Description |
|-------|------|-------------|
| `itemKey` | `string` | Unique key: `rice_kg`, `water_liters`, `meds_units`, `kits_units` |
| `label` | `string` | Display name, e.g. `"Rice"` |
| `unit` | `string` | Unit of measurement: `"kg"`, `"L"`, `"units"` |
| `pricePerUnit` | `float` | Price in Philippine Pesos (PHP) |
| `updatedAt` | `string` | ISO timestamp of last update |

**Example Response:**
```json
[
  {
    "itemKey": "rice_kg",
    "label": "Rice",
    "unit": "kg",
    "pricePerUnit": 50.0,
    "updatedAt": "2026-03-07T04:57:49.066270"
  },
  {
    "itemKey": "water_liters",
    "label": "Water",
    "unit": "L",
    "pricePerUnit": 15.0,
    "updatedAt": "2026-03-07T04:57:49.066274"
  },
  {
    "itemKey": "meds_units",
    "label": "Medicine Kits",
    "unit": "units",
    "pricePerUnit": 500.0,
    "updatedAt": "2026-03-07T04:57:49.066277"
  },
  {
    "itemKey": "kits_units",
    "label": "Hygiene Kits",
    "unit": "units",
    "pricePerUnit": 350.0,
    "updatedAt": "2026-03-07T04:57:49.066278"
  }
]
```

---

### PATCH /prices/{item_key}

**ADMIN** — Update the unit price for a relief goods item.

**Path Parameters:**

| Parameter | Type | Required | Valid Values | Description |
|-----------|------|----------|--------------|-------------|
| `item_key` | `string` | Yes | `rice_kg`, `water_liters`, `meds_units`, `kits_units` | Item identifier |

**Request Body:**

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `pricePerUnit` | `float` | Yes | >= 0 | New price in PHP |

**Example Request:**
```json
{
  "pricePerUnit": 55.0
}
```

**Response `200 OK`:** Updated `PriceResponse` object.

```json
{
  "itemKey": "rice_kg",
  "label": "Rice",
  "unit": "kg",
  "pricePerUnit": 55.0,
  "updatedAt": "2026-03-07T05:30:00.000000"
}
```

**Error Responses:**

| Status | Detail |
|--------|--------|
| `400` | Price must be non-negative |
| `401` | Missing or invalid token |
| `403` | User is not an admin |
| `404` | Unknown item_key |

---

## 8. Admin

### GET /admin/users

**ADMIN** — List all users with their assigned cities.

**Response `200 OK`:** Array of `UserWithCities` objects.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | User ID |
| `email` | `string` | Email address |
| `fullName` | `string` | Display name |
| `role` | `string` | `"admin"` or `"lgu"` |
| `cities` | `string[]` | List of assigned city pcodes |

**Example Response:**
```json
[
  {
    "id": 1,
    "email": "admin@philiready.ph",
    "fullName": "System Admin",
    "role": "admin",
    "cities": []
  },
  {
    "id": 2,
    "email": "lgu_cebu@philiready.ph",
    "fullName": "Cebu DRRMO Officer",
    "role": "lgu",
    "cities": ["1380600000", "102801000"]
  }
]
```

---

### POST /admin/users/{id}/cities

**ADMIN** — Assign city edit access to a user. Idempotent -- already-assigned cities are skipped.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | `integer` | Yes | Target user's ID |

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pcodes` | `string[]` | Yes | List of city PSGC codes to assign |

**Example Request:**
```json
{
  "pcodes": ["1380600000", "102801000"]
}
```

**Response `201 Created`:**

| Field | Type | Description |
|-------|------|-------------|
| `message` | `string` | Success message |
| `added` | `string[]` | Newly assigned pcodes |
| `skipped` | `string[]` | Already-assigned pcodes (no change) |
| `invalid` | `string[]` | Pcodes not found in the database |

**Example Response:**
```json
{
  "message": "City access updated for user lgu_cebu@philiready.ph",
  "added": ["1380600000"],
  "skipped": ["102801000"],
  "invalid": []
}
```

**Error Responses:**

| Status | Detail |
|--------|--------|
| `401` | Missing or invalid token |
| `403` | User is not an admin |
| `404` | Target user ID not found |

---

### DELETE /admin/users/{id}/cities/{pcode}

**ADMIN** — Remove a specific city from a user's edit access.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | `integer` | Yes | Target user's ID |
| `pcode` | `string` | Yes | City PSGC code to remove |

**Example Request:**
```
DELETE /api/v1/admin/users/2/cities/1380600000
```

**Response `200 OK`:**
```json
{
  "message": "Removed access to '1380600000' for user 2"
}
```

**Error Responses:**

| Status | Detail |
|--------|--------|
| `401` | Missing or invalid token |
| `403` | User is not an admin |
| `404` | User does not have access to the specified city |

---

## 9. Weather

### GET /weather

**PUBLIC** — Get a 7-day weather forecast (Manila default). Data is cached daily.

**Response `200 OK`:** Array of 7 `WeatherDay` objects.

| Field | Type | Description |
|-------|------|-------------|
| `date` | `string` | ISO date, e.g. `"2026-03-07"` |
| `precipMm` | `float` | Total precipitation (mm) |
| `windKmh` | `float` | Maximum wind speed (km/h) |
| `alert` | `boolean` | `true` if precipitation > 30mm (PAGASA Orange) |

**Example Response:**
```json
[
  {
    "date": "2026-03-07",
    "precipMm": 5.2,
    "windKmh": 18.4,
    "alert": false
  },
  {
    "date": "2026-03-08",
    "precipMm": 42.1,
    "windKmh": 35.6,
    "alert": true
  }
]
```

---

## 10. Health Check

### GET /health

> **Note:** This endpoint is at the root level, NOT under `/api/v1`.

**PUBLIC** — Deployment health check.

**Example Request:**
```
GET http://localhost:8000/health
```

**Response `200 OK`:**
```json
{
  "status": "ok",
  "service": "philiready-api",
  "version": "2.0.0"
}
```

---

## Common Error Format

All error responses follow this shape:

```json
{
  "detail": "Error message describing what went wrong"
}
```

| Status Code | Meaning |
|-------------|---------|
| `400` | Bad Request -- invalid input or validation error |
| `401` | Unauthorized -- missing or invalid JWT token |
| `403` | Forbidden -- insufficient permissions (e.g. not admin) |
| `404` | Not Found -- resource doesn't exist |
| `409` | Conflict -- duplicate entry (e.g. email already registered) |
| `500` | Internal Server Error -- unexpected server failure |

---

## Quick Reference: All Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/auth/login` | PUBLIC | Login, get JWT token |
| `POST` | `/auth/register` | ADMIN | Create user account |
| `GET` | `/auth/me` | AUTH | Current user profile |
| `GET` | `/cities/{pcode}` | PUBLIC | City detail + peak demand |
| `PATCH` | `/cities/{pcode}` | AUTH+CITY | Edit city parameters |
| `GET` | `/forecast/{pcode}` | PUBLIC | 7-day demand forecast |
| `GET` | `/map/demand-heat` | PUBLIC | All cities demand scores |
| `POST` | `/simulate` | PUBLIC | Simulated disaster scores |
| `GET` | `/simulator/forecast` | PUBLIC | Custom city forecast |
| `GET` | `/prices` | PUBLIC | List item prices |
| `PATCH` | `/prices/{item_key}` | ADMIN | Update an item price |
| `GET` | `/admin/users` | ADMIN | List all users |
| `POST` | `/admin/users/{id}/cities` | ADMIN | Assign city access |
| `DELETE` | `/admin/users/{id}/cities/{pcode}` | ADMIN | Remove city access |
| `GET` | `/weather` | PUBLIC | 7-day weather forecast |

---

## Notes for Frontend Integration

### camelCase Convention
All JSON response keys are **camelCase** (e.g. `riceLower`, `totalCost`, `precipMm`, `riskScore`, `pricePerUnit`).
Request bodies accept both **camelCase** and **snake_case** (e.g. `floodZone` and `flood_zone` both work).

### Storing Simulator State in URL
The simulator endpoint (`GET /simulator/forecast`) is designed so all parameters are query strings. Store the simulation state directly in the browser URL:

```
https://example.com/simulator?population=500000&severity=3&is_coastal=1
```

Users can bookmark or share these URLs without any data loss.

### JWT Token Storage
- Store the `accessToken` in `localStorage` or a secure cookie.
- The token expires after 24 hours (configurable via `JWT_EXPIRY_MINUTES`).
- Include it in every authenticated request: `Authorization: Bearer <token>`

### Cost Calculations
- Costs are calculated server-side using prices from the `item_prices` table.
- Cost = demand quantity x price per unit.
- `totalCost` = sum of all item costs for that day.
- All costs are in **Philippine Pesos (PHP)**.

### Relief Items Reference

| Key | Label | Unit | Default Price (PHP) |
|-----|-------|------|---------------------|
| `rice_kg` | Rice | kg | 50.00 |
| `water_liters` | Water | L | 15.00 |
| `meds_units` | Medicine Kits | units | 500.00 |
| `kits_units` | Hygiene Kits | units | 350.00 |
