# 🗺 White Label Roadmap: Transitioning Anti-Taro to a Multi-tenant SaaS

This document outlines the technical steps required to transform the current monolithic bot into a scalable White Label platform where other communities and experts can launch their own "Anti-Taro" instances.

## Phase 1: Database & Data Isolation (Weeks 1-2)
*   **Tenant Management:**
    *   Create a `tenants` table in Supabase. Fields: `id`, `slug`, `owner_id`, `vk_token`, `group_id`, `config` (JSONB), `theme` (JSONB).
    *   Add `tenant_id` column to all user-related tables (`vk_esoteric_users`, `events`, `feedbacks`).
    *   Update all database queries to include `tenant_id` filter (RLS - Row Level Security in Supabase is ideal for this).
*   **Redis Prefixing:**
    *   Implement a wrapper for Redis client that automatically prefixes all keys with `{tenant_id}:`.

## Phase 2: Dynamic Core & Dispatching (Weeks 3-4)
*   **Multi-Bot Dispatcher:**
    *   Modify `main.py` to handle incoming webhooks from multiple VK groups.
    *   Implement a lookup mechanism to identify the `tenant_id` based on the `group_id` or `secret` in the webhook payload.
*   **Configuration Provider:**
    *   Replace direct `os.getenv` calls for bot-specific settings with a `ConfigService`.
    *   Cache tenant-specific configs in Redis with a short TTL.
*   **Persona Isolation:**
    *   Allow each tenant to have a custom subset of skins or override existing skin propmts/visuals.

## Phase 3: Visual & AI Customization (Weeks 5-6)
*   **Theming Engine (Pillow):**
    *   Abstract colors, fonts, and base assets in `modules/utils/visual.py`.
    *   Enable per-tenant asset uploading (logos, backgrounds) for cards and PDF reports.
*   **Prompt Templating:**
    *   Refactor `ai/logic.py` and `prompts/` to use dynamic placeholders (e.g., `{{bot_name}}`, `{{community_link}}`) injected at runtime.

## Phase 4: Monetization & Administration (Weeks 7-8)
*   **Payment Routing:**
    *   Update `modules/payments/` to support tenant-specific YooKassa/VK Pay credentials.
    *   Implement a centralized fee tracking system (billing for White Label users).
*   **White Label Admin Dashboard:**
    *   Create a specialized interface for White Label owners to manage their bot, view their own analytics, and customize their skins.

## Phase 5: Infrastructure & Scaling (Ongoing)
*   **Deployment Automation:**
    *   CI/CD pipelines that can deploy new instances or update shared core logic without downtime.
*   **Global Health Monitoring:**
    *   Unified Sentry/Logging system with tenant-level filtering.
