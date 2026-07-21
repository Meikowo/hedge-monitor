-- M4a POC 首份真实年报反馈 + Supabase Advisor 安全收紧
alter table public.periodic_metric_items
  drop constraint if exists periodic_metric_items_metric_type_check;
alter table public.periodic_metric_items
  add constraint periodic_metric_items_metric_type_check check (metric_type in (
    'period_purchase_amount','period_sale_amount','period_pnl','ending_balance',
    'net_asset_ratio','derivative_asset_fv','derivative_liability_fv',
    'margin_end_cash','margin_peak_reported','collateral_end_fair_value',
    'credit_facility_used_end','option_premium_usage_peak','notional_end_reported',
    'notional_peak_reported','contract_quantity_end','oci_amount',
    'reclassification_amount'));

-- 视图按调用者权限执行，避免绕过底表 RLS。
alter view public.v_ann_flow set (security_invoker = true);
alter view public.v_events set (security_invoker = true);

-- 触发器函数不依赖对象查找，固定空 search_path 消除可变路径风险。
alter function public.set_updated_at() set search_path = '';

