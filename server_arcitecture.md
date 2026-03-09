# Inclinic Server Architecture

## Overview
This document describes the infrastructure architecture for **Inclinic**.

The system consists of:

- One Application Server (EC2)
- Two Databases
- Centralized configuration using `settings.py`

---

## Architecture Diagram (ASCII)
```
                      ┌─────────────────────────┐
                      │        Users / API       │
                      └────────────┬────────────┘
                                   │
                                   │ HTTP / HTTPS
                                   ▼
            ┌─────────────────────────────────────┐
            │            AWS EC2 SERVER            │
            │-------------------------------------│
            │  Inclinic Application               │
            │                                     │
            │  - Backend Services                 │
            │  - Business Logic                   │
            │  - settings.py (All DB configs)     │
            │                                     │
            │  Local/Default Database             │
            │  (Inclinic Local DB)                │
            └──────────────┬──────────────────────┘
                           │
                           │ Secure DB Connection
                           │
                           ▼
            ┌─────────────────────────────────────┐
            │            AWS RDS                   │
            │-------------------------------------│
            │            Master Database          │
            │                                     │
            │  - Central Data Storage             │
            │  - Production Master DB             │
            └─────────────────────────────────────┘

```


---

## Components

### 1. Application Server

**Service:** AWS EC2  
**Hosted Application:** Inclinic

Responsibilities:

- Runs application services
- Handles API requests
- Manages business logic
- Maintains local database
- Reads connection configs from `settings.py`

---

### 2. Databases

#### a. Master Database (RDS)

- Hosted on AWS RDS
- Acts as the **Primary/Master Database**
- Stores production data
- Connected remotely from EC2

#### b. Local Database (EC2)

- Hosted inside EC2 server
- Default Inclinic database
- Used for:
  - Local processing
  - Fast internal operations
  - Temporary or service data

