# PROJECT.md â€”â€” å¥—ä¿ç›‘æŽ§ï¼ˆhedge-monitorï¼‰é¡¹ç›®ä¸Šä¸‹æ–‡ä¸»æ–‡ä»¶ v2.11

> ç”¨é€”ï¼šæ¯æ¬¡ä¸Ž Claude å¼€æ–°ä¼šè¯æ—¶ä¸Šä¼ æœ¬æ–‡ä»¶ï¼ˆæˆ–æ”¾å…¥ Claude Project çŸ¥è¯†åº“ï¼‰ã€‚
> ç”±ä½ ç»´æŠ¤ï¼›æ¯æ¬¡ä¼šè¯ç»“æŸè®© Claude è¾“å‡ºæ›´æ–°æ®µè½ï¼Œä½ æ›¿æ¢åŽ commitã€‚
> éœ€æ±‚çš„å”¯ä¸€åŸºå‡†æ˜¯ docs/PRD.mdï¼ˆv1.7ï¼‰ï¼Œæœ¬æ–‡ä»¶è®°å½•"çŽ°çŠ¶ä¸Žå†³ç­–"ï¼Œä¸å¤è¿°éœ€æ±‚ã€‚
> æœ€åŽæ›´æ–°ï¼š2026-08-11ï¼ˆM6a é¦–æ‰¹å®˜æ–¹é£Žé™©æ¡ˆä¾‹çºµå‘åˆ‡ç‰‡ï¼‰

## 1. ä¸€å¥è¯å®šä½

è‡ªç”¨ä¸“ä¸šç ”ç©¶å·¥å…·ï¼šA è‚¡ä¸Šå¸‚å…¬å¸å¥—ä¿æŠ«éœ²çš„æ—¥æ›´ç›‘æŽ§ã€ç»“æž„åŒ–æŠ½å–ã€ã€Œè®¡åˆ’ vs å®žé™…ã€
å¯¹æ¯”åˆ†æžï¼Œä»¥åŠè¡ç”Ÿå“ç›¸å…³ç›‘ç®¡é—®è¯¢ã€å¤„ç½šå’Œé‡å¤§é£Žé™©æ¡ˆä¾‹ç›‘æµ‹ã€‚æœåŠ¡æœŸè´§ç ”ç©¶æ‰€ç ”ç©¶å‘˜çš„
é£Žé™©ç®¡ç†ç ”ç©¶ä¸Žå±•ä¸šçº¿ç´¢éœ€æ±‚ã€‚å•ç”¨æˆ·ï¼Œæ— å¯¹å¤–æœåŠ¡ã€‚

## 2. æž¶æž„ä¸ŽæŠ€æœ¯æ ˆï¼ˆR0 å®šç¨¿ï¼‰

- **é‡‡é›†**ï¼šGitHub Actionsï¼ˆPythonï¼‰â†’ å·¨æ½® hisAnnouncementï¼ˆæ ‡é¢˜å±‚ï¼‰+
  fulltextSearchï¼ˆæ­£æ–‡å®¡è®¡å±‚ï¼‰ã€‚âœ… Actions ç›´è¿žå·¨æ½®å·²é•¿æœŸéªŒè¯å¯è¾¾ã€‚
- **æŠ½å–**ï¼šMiniMax-M3ï¼ŒOpenAI å…¼å®¹æŽ¥å£ `https://api.minimaxi.com/v1`ã€‚
  å…¬å‘Šç®¡çº¿ä½¿ç”¨ adaptive thinkingï¼›M4 å®šæœŸæŠ¥å‘Šæ”¹ä¸ºæ˜¾å¼ç¦ç”¨ thinking + å››æ®µçŸ­ JSONï¼Œ
  é˜²æ­¢é•¿è¾“å‡ºæˆªæ–­ï¼Œå¹¶æ”¯æŒæŒ‰çŸ­æ‰¹æ¬¡é‡è·‘ã€‚Actions ä¸Žæœ¬åœ°æŽ¢æ´»å‡å·²éªŒè¯å¯è¾¾ã€‚
- **å­˜å‚¨**ï¼šSupabase Postgresï¼ŒPostgREST REST ç›´å†™ï¼ˆservice_roleï¼‰ï¼Œ
  è¿ç§»æ–‡ä»¶åœ¨ db/ ä¸”ä¸ºå”¯ä¸€äº‹å®žæºï¼ˆ"ç…§ä»“åº“å³å¯é‡å»ºåº“"ï¼‰ã€‚
- **å…¬å¸ç»´è¡¨**ï¼šiFind æ‰‹åŠ¨å¯¼å‡ºï¼ˆå­£åº¦åˆ·æ–°ï¼‰ä¸ºæƒå¨æ¥æºï¼Œå«ä¼ä¸šæ€§è´¨+åŒèŠ±é¡ºä¸‰çº§è¡Œä¸šï¼Œ
  ä¸€å¹¶è§£å†³äº†æ—§ #7 ent_type è¡¥å…¨ã€‚akshare/ä¸œè´¢è·¯çº¿å·²åºŸå¼ƒï¼ˆActions ä¸å¯è¾¾ï¼Œä¸¤æ¬¡å®žæµ‹è¯ä¼ªï¼‰ã€‚
- **å‰ç«¯**ï¼šGitHub Pages é™æ€ç«™ï¼ˆM3 é‡åšï¼‰ï¼Œæ•°æ®é€šè·¯å®šä¸º **anon key ç›´è¿ž
  Supabase + RLS åªè¯»**ï¼ˆç­–ç•¥å·²éš 001_init.sql å°±ä½ï¼‰ï¼›è¯»å–å¥‘çº¦=è§†å›¾
  v_ann_flow / v_eventsã€‚è®¾è®¡è¯­è¨€æŒ‰ PRD 7.6ã€Œç ”æŠ¥çº¸æ„Ÿçš„æ•°æ®ç»ˆç«¯ã€ã€‚
- **è°ƒåº¦**ï¼šdailyï¼ˆåŒ—äº¬03:00ï¼‰è´Ÿè´£å…¬å‘Šé‡‡é›†ï¼›extract æ¯6å°æ—¶è‡ªåŠ¨æŠ½å–æœ€å¤š600æ¡
  pendingï¼›auditï¼ˆæ¯æœˆ1æ—¥ï¼‰è‡ªåŠ¨è¡¥æ¼ï¼›backfill / import-companies / probe æ‰‹åŠ¨è§¦å‘ã€‚
- **é£Žé™©æ¡ˆä¾‹ï¼ˆv1.4ï¼‰**ï¼šå®˜æ–¹æ¡ˆä¾‹ä½¿ç”¨ç‹¬ç«‹æ¥æºé€‚é…å™¨ã€ç‹¬ç«‹å››è¡¨ä¸Žç‹¬ç«‹ Actions
  concurrency groupï¼›åª’ä½“æœç´¢ç»“æžœå…ˆè¿›å…¥ service_role ç§æœ‰å€™é€‰å±‚ï¼Œåªæœ‰é€šè¿‡ç¡®å®šæ€§æ¥æºä¸Ž
  ç›¸å…³æ€§é—¨æ§›çš„å®‰å…¨å­—æ®µæ‰æŠ•å½±åˆ° anon åªè¯»å…¬å¼€å±‚ã€‚ä¸¤å±‚è¯æ®ä¸æ··ç®—ï¼Œäººå·¥åªåšè´¨é‡æŠ½æ£€ã€‚

## 3. æ•°æ®æ¨¡åž‹ï¼ˆä¸‰å±‚ï¼Œå¥‘çº¦è¯¦è§ docs/schema_snapshot.mdï¼‰

```
companies(ç»´è¡¨)   announcements(å…¬å‘Šå±‚)
                        â”‚ 1:1
                  extractions(æŠ½å–å±‚) â”€â”€ quota_items(é¢åº¦æ˜Žç»†ï¼Œåˆ†å£å¾„)
                        â”‚ æ´¾ç”Ÿèšåˆï¼ˆbuild_events å…¨é‡é‡å»ºï¼‰
                  hedge_events(äº‹ä»¶å±‚) â”€â”€ event_members(æŒ‚é å…³ç³»)
```

ä¸‰ä¸ªè€é—®é¢˜çš„è½åœ°æ–¹å¼ï¼š
1. **æŸ¥å…¨çŽ‡**ï¼šä¸‰å±‚å¬å›žå…¨è‡ªåŠ¨â€”â€”L1 æ ‡é¢˜è¯è¡¨ï¼ˆconfig/keywords.ymlï¼Œ13è¯ï¼‰é€è¯æŸ¥+åŽ»é‡ï¼›
   L2 æœˆåº¦å…¨æ–‡å®¡è®¡è‡ªåŠ¨è¡¥æžæ¼æ£€å…¥åº“ï¼›L3 LLM is_hedge_related å…œåº•è¿‡æ»¤å™ªéŸ³ã€‚åŠ è¯=æ”¹é…ç½®ã€‚
2. **äº‹ä»¶åŽ»é‡**ï¼šhedge_events ä¸€è¡Œ=ä¸€æ¬¡å¥—ä¿å†³ç­–ï¼›è¿›å±•/è‚¡ä¸œå¤§ä¼šå†³è®®ç­‰æŒ‚é è€Œéžæ–°å¢žï¼›
   å…¨éƒ¨ç»Ÿè®¡å£å¾„åº”åŸºäºŽäº‹ä»¶å±‚æˆ–æ˜Žç¡®å£°æ˜ŽåŸºäºŽå…¬å‘Šå±‚ã€‚
3. **é¢åº¦å£å¾„**ï¼šquota_items ç»“æž„åŒ–äº”å…ƒç»„ï¼ˆscope/basis/amount/currency/rawï¼‰ï¼Œ
   basis é—­é›†æžšä¸¾ï¼ˆä¿è¯é‡‘å ç”¨/ä¸šåŠ¡æ€»é¢/åä¹‰æœ¬é‡‘/åˆçº¦ä»·å€¼/å…¶ä»–/æœªæŠ«éœ²ï¼‰+ CHECK çº¦æŸï¼›
   æ¯æ¡é¢åº¦å¸¦åŽŸæ–‡æ‘˜å½•ã€é¡µç ä¸Ž**ç¨‹åºå›žéªŒ**åŒæ ‡å¿—ï¼ˆamount_verified/quote_verifiedï¼Œ
   PRD 5.7 ç¬¬äºŒå±‚é˜²çº¿å·²åœ¨å…¬å‘Šç®¡çº¿æå‰è½åœ°ï¼‰ã€‚

## 4. å…³é”®å†³ç­–è®°å½•ï¼ˆADRï¼Œä¸€äº‹ä¸€è¡Œï¼Œè¯¦æƒ…è§å¯¹åº” worklogï¼‰

- 2026-07-08ï¼šcompanies æž„å»ºç§»å‡º Actionsï¼ˆä¸œè´¢/akshare æœºæˆ¿ IP è¢«æ‹‰é»‘ï¼‰ï¼›ç¡®ç«‹
  ã€Œå›½å†…å•†ä¸šæŽ¥å£å¯è¾¾æ€§å¿…é¡»é€æºå®žæµ‹ã€åŽŸåˆ™ã€‚
- 2026-07-13ï¼š**R0 ä»Žå¤´é‡å»º**â€”â€”æ”¾å¼ƒæ—§åº“å­˜é‡ï¼ˆçº¦4000+å…¬å‘Š/124æŠ½å–ï¼‰ï¼Œç†ç”±ï¼šæ–°è¯è¡¨
  å¬å›žæœ¬å°±è¦æ±‚é‡æŠ“ã€æ–°æ•°æ®æ¨¡åž‹è¦æ±‚é‡æŠ½ã€æ—§æŠ½å–æ— é¡µç è¯æ®ä¸Žå£å¾„æ˜Žç»†ã€‚æ—§ä»£ç å­˜æ¡£
  legacy-demo åˆ†æ”¯ã€‚
- 2026-07-13ï¼šcompanies æƒå¨æ¥æºå®šç¨¿ä¸º iFind å­£åº¦å¯¼å‡ºï¼›build_companies v4 è·¯çº¿åºŸå¼ƒã€‚
- 2026-07-13ï¼šæŠ½å–å±‚ä¸Žäº‹ä»¶å±‚åˆ†ç¦»ï¼›äº‹ä»¶å±‚ä¸º**æ´¾ç”Ÿè¡¨**ï¼ˆç¡®å®šæ€§é”®+å…¨é‡é‡å»ºï¼‰ï¼Œ
  åˆ†ç»„è§„åˆ™å¯éšæ—¶æ¼”è¿›è€Œä¸ä¼¤åº•å±‚æ•°æ®ã€‚
- 2026-07-13ï¼šæŠ½å–èŒƒå›´å«åˆ¶åº¦/å¯è¡Œæ€§/è¿›å±•ï¼ˆis_hedge_related=true + ann_role åŒºåˆ†ï¼‰ï¼Œ
  ä»…"è®¡åˆ’-è‘£äº‹ä¼š/è‚¡ä¸œå¤§ä¼š"è´¡çŒ®äº‹ä»¶é¢åº¦ï¼›irrelevant ç”± LLM åˆ¤å®šè‡ªåŠ¨æ‰“æ ‡ã€‚
- 2026-07-13ï¼šç§˜é’¥çº¢çº¿ç»´æŒï¼ˆå€¼ä¸è¿›ä»“åº“/å¯¹è¯/å‰ç«¯ï¼‰ï¼ŒMiniMax key ç»Ÿä¸€å˜é‡å LLM_API_KEYã€‚

## 5. ç§˜é’¥æ¸…å•ï¼ˆåªè®°åå­—ä¸Žä½ç½®ï¼‰

- GitHub repo Secretsï¼šSUPABASE_URLã€SUPABASE_SERVICE_ROLE_KEYã€LLM_API_KEYã€TAVILY_API_KEY
- æœ¬åœ° .envï¼ˆå·² gitignoreï¼‰ï¼šåŒä¸Šå››é¡¹
- å‰ç«¯ï¼ˆM3 èµ·ï¼‰åªå…è®¸ anon key + RLS åªè¯»

## 6. è¿›åº¦æ¸…å•ï¼ˆ2026-08-11 ç‰ˆï¼‰

| # | äº‹é¡¹ | çŠ¶æ€ |
|---|------|------|
| R0.1 | ä¸‰å±‚æ•°æ®æ¨¡åž‹ + è¿ç§» + è§†å›¾ + RLSï¼ˆdb/ï¼‰ | âœ… æ–° Supabase å·²æ‰§è¡Œå¹¶éªŒæ”¶ |
| R0.2 | é‡‡é›†/å®¡è®¡/æŠ½å–/äº‹ä»¶/å¯¼å…¥äº”æ¡ç®¡çº¿ + 6 workflows | âœ… å·²åˆå¹¶ main |
| R0.3 | ç”¨æˆ·ä¾§éƒ¨ç½² 8 æ­¥ï¼ˆREADME é¦–æ¬¡éƒ¨ç½²èŠ‚ï¼‰ | âœ… å·²å®Œæˆæ ¸å¿ƒéƒ¨ç½² |
| R0.4 | MiniMax@Actions æŽ¢æ´»ç»“è®º | âœ… Actions æŽ¢æ´»æˆåŠŸ |
| R1 | å›žå¡« 2026 + æ¸…ç§¯åŽ‹ + é¦–è½® verify.sql å…¨é‡å›žè´´ | âœ… 2026 å…¬å‘Šç§¯åŽ‹ä¸Žå¤±è´¥é¡¹å·²æ¸…é›¶ï¼Œäº‹ä»¶å±‚é‡å»ºå®Œæˆ |
| R2 | é€å¹´å›žå¡« 2025â†’2021ï¼Œæ¯å¹´é…æŠ½å–æ¸…é›¶ï¼ˆæŒ‚æœºï¼‰ | ðŸ”„ 2025â€”2022 å·²å®Œæˆä¸”æ—  pendingï¼›2022â€”2023 å°šä½™ 7 æ¡ failedï¼›2021 å°šæœªå›žå¡« |
| R3 | æŠ½å–è´¨é‡é‡‘æ ‡å‡†è¯„æµ‹ï¼š50 ä»½äººå·¥æ ‡æ³¨ vs æŠ½å–ç»“æžœï¼Œå­—æ®µçº§å‡†ç¡®çŽ‡ | â¸ å»ºè®® R1 åŽ |
| M3 | å‰ç«¯æ­£å¼ç‰ˆï¼ˆPRD 7.x + è®¾è®¡è¯­è¨€ 7.6ï¼Œå…ˆè§†è§‰æ–¹å‘ç¨¿å†è½ç ï¼‰ | âœ… v1 å·²éƒ¨ç½²ï¼šé«˜å¯†åº¦äº‹ä»¶ç ”ç©¶ + è¯æ®è¯¦æƒ… + æ•°æ®çœ‹æ¿ + CSV å¯¼å‡º |
| M4a/b | å®šæœŸæŠ¥å‘Šï¼ˆå¹´æŠ¥+åŠå¹´æŠ¥ï¼‰é‡‡é›†ä¸Žè§£æž | ðŸ”„ 2025FY æ­£å¼æ±  1,812 å®¶ï¼šå·²å‘çŽ° 1,767 å®¶ï¼Œå·²æŠ½å– 378 å®¶ã€å¦æœ‰ 448 å®¶å·²å®šä½ï¼›1,590 æ¡æ•°å€¼å…¨éƒ¨åŒå›žéªŒï¼›æ­£å¼å‰ç«¯ v0.2 å·²éƒ¨ç½² |
| M5 | è®¡åˆ’ vs å®žé™…ä¸‰ç»´æ ¸å¯¹ï¼ˆPRD 5.6ï¼‰ | ðŸ”„ å‰ç«¯å·²å±•ç¤ºå…¬å‘Šå€™é€‰å…³è”ï¼›é‡‘é¢/å£å¾„è‡ªåŠ¨åŒ¹é…ä»å¾…M4æ ·æœ¬ç¨³å®šåŽå®žçŽ° |
| M6a | è‡ªåŠ¨åŒ–è¡ç”Ÿå“é£Žé™©æ¡ˆä¾‹ POCï¼ˆPRD 5.8ï¼‰ | ðŸ”„ é¦–æ‰¹ 3 ä¸ªå®˜æ–¹æ¡ˆä¾‹çºµå‘åˆ‡ç‰‡å·²å…¥åº“å¹¶é€å­—å›žéªŒï¼›æ¯æ—¥è‡ªåŠ¨å‘å¸ƒå·¥ä½œæµå·²å»ºç«‹ï¼Œä¸‹ä¸€æ­¥æ‰©å±•å®˜æ–¹æ¥æºã€å€™é€‰é‡ä¸Žäººå·¥æŠ½æ£€è´¨é‡é—¸é—¨ |
| M6b | é£Žé™©æ¡ˆä¾‹åŽ†å²æ‰©å±•ã€å¢žé‡ç›‘æµ‹ä¸Žå‰ç«¯ï¼ˆPRD 7.8ï¼‰ | âœ… æ­£å¼å‰ç«¯ v1 å·²å®žçŽ°ï¼šå®˜æ–¹/åª’ä½“åŒè¯æ®å±‚ã€ç­›é€‰ã€é«˜å¯†åº¦åˆ—è¡¨ã€è¯¦æƒ…å’Œ CSVï¼›50 ä»½å€™é€‰/10 æ¡ˆä¾‹/90% ç²¾ç¡®çŽ‡ä¿ç•™ä¸ºå®˜æ–¹ç®¡çº¿æ‰©é‡é—¸é—¨ï¼Œä¸å†é˜»å¡žçœŸå®žåª’ä½“å±‚ä¸Šçº¿ |

## 7. é£Žé™©ä¸Žå·²çŸ¥å±€é™

1. **æ¨¡åž‹å…±äº«é¢åº¦**ï¼šMiniMax@Actions å·²é•¿æœŸè¿è¡ŒéªŒè¯å¯è¾¾ï¼›å…¬å‘Šã€M4 ä¸Žæœªæ¥ M6 å…±äº«å¥—é¤é¢åº¦ï¼Œ
   æ–°ç®¡çº¿å¿…é¡»åˆ†åˆ«è®¾ç½®æ‰¹æ¬¡ä¸Šé™ã€è®°å½•è°ƒç”¨é‡å¹¶é¿å…åŒæ—¶å æ»¡é…é¢ã€‚
2. **äº‹ä»¶åˆ†ç»„ v1 æ˜¯å¯å‘å¼**ï¼šåŒå¹´åŒç±»è¿½åŠ é¢åº¦ä¼šå¹¶å…¥åŒä¸€äº‹ä»¶ï¼ˆå¤šæ•°åœºæ™¯åˆç†ï¼‰ï¼›
   è·¨å¹´å¤šæœŸè®¡åˆ’ä»¥æ ‡ç­¾å¹´é”šå®šã€‚å¾…çœŸå®žæ•°æ®éªŒè¯åŽåœ¨ build_events v2 ç»†åŒ–â€”â€”æ´¾ç”Ÿè¡¨
   è®¾è®¡ä¿è¯é‡ç®—é›¶æˆæœ¬ã€‚
3. **é‡å»ºæˆæœ¬**ï¼šåŽ†å² 5 å¹´é‡æŠ½çº¦ 1.5â€“2.5 ä¸‡æ¬¡ LLM è°ƒç”¨ï¼ˆå¤šæ•°å…¬å‘Š irrelevant åˆ¤å®š
   å¾ˆä¾¿å®œï¼‰ï¼ŒMiniMax å¹´è´¹å¥—é¤å†…é¢„è®¡å¯coveredï¼›é€å¹´æŽ¨è¿›å¯éšæ—¶è§‚å¯Ÿç”¨é‡ã€‚
4. **å·¨æ½®é£ŽæŽ§**ï¼šæ‰€æœ‰å·¨æ½® workflow å…±ç”¨ concurrency group ä¸²è¡ŒåŒ–ï¼›é€€é¿å·²å†…ç½®ï¼›
   æ•´è½®å¤±è´¥ç­‰ 1 å°æ—¶å¹‚ç­‰é‡è·‘ã€‚
5. **Supabase å…è´¹æ¡£**ï¼šdaily æ¯æ—¥å†™åº“å¤©ç„¶ä¿æ´»ï¼›ç•™æ„ Actions æ–­æ¡£ã€‚
6. **å…¬å¼€æ€§**ï¼šanon å¯è¯»å…¨åº“ï¼ˆè‡ªç”¨æŽ¥å— obscurityï¼‰ï¼›å¦‚éœ€åŠ å£ä»¤åœ¨ M3 è®¨è®ºã€‚
7. **iFind è¡¨æ—¶æ•ˆ**ï¼šå­£åº¦åˆ·æ–°ï¼Œé€€å¸‚/æ›´å/æ€§è´¨å˜æ›´åœ¨åˆ·æ–°é—´éš”å†…æ»žåŽï¼ˆå¯æŽ¥å—ï¼‰ã€‚
8. **å¹´æŠ¥å¤æ‚è¡¨æ ¼è¯æ®**ï¼šå½“å‰æ­£å¼å‰ç«¯åªè¯»å– `value_verified=true` ä¸”
   `quote_verified=true` çš„äº‹å®žï¼›è·¨é¡µè¡¨å¤´ã€å•ä½ç»§æ‰¿å’Œæ¢è¡Œæ ‡é¢˜å·²æ”¯æŒï¼Œä½†æ–°è¡¨åž‹ä»é¡»
   å…ˆé€šè¿‡ POC å®¡è®¡å†æ‰©å¼ ã€‚
9. **é£Žé™©æ¥æºå¼‚æž„ä¸Žé¡µé¢å˜åŠ¨**ï¼šäº¤æ˜“æ‰€ã€è¯ç›‘ä¼šåŠæ´¾å‡ºæœºæž„é¡µé¢ç»“æž„ä¸åŒï¼Œé€‚é…å™¨å¿…é¡»é€æº
   æµ‹è¯•ã€ä¿å­˜åŽŸå§‹ URL/å“ˆå¸Œï¼Œå¹¶å…è®¸å•ä¸€æ¥æºæ•…éšœæ—¶ç‹¬ç«‹é‡è¯•ã€‚
10. **è¡ç”Ÿå“ç›¸å…³æ€§è¯¯åˆ¤**ï¼šä¸€èˆ¬ç»è¥é—®è¯¢æˆ–å¤„ç½šä¸å¾—å› å…¬å¸æ›¾åšå¥—ä¿è€Œè¿›å…¥é£Žé™©æ¡ˆä¾‹åº“ï¼›
    å¿…é¡»ç”±åŽŸæ–‡ä¸­çš„è¡ç”Ÿå“ä¸šåŠ¡è¯æ®é€šè¿‡ç›¸å…³æ€§é—¸é—¨ã€‚SSE å°æ ·å·²æŽ’é™¤â€œè¯åˆ¸æœŸè´§å¸‚åœºè¯šä¿¡
    æ¡£æ¡ˆâ€ã€èˆªè¿â€œèˆ±ä½äº’æ¢â€ã€åº”æ”¶æ¬¾â€œè¿œæœŸç»“ç®—â€ã€è¿œæœŸé€€æ¢è´§ã€è‚¡ç¥¨æœŸæƒæ¿€åŠ±åŠ
    â€œè¿‡æ¸¡æœŸæƒç›Šâ€ç­‰éžè¡ç”Ÿå“è¯­å¢ƒã€‚
11. **å¹¶è¡Œèµ„æºå†²çª**ï¼šM4 ä¸Ž M6 å¯å¹¶è¡Œå†™å„è‡ªæ•°æ®åŸŸï¼Œä½†å…±äº«è¿ç§»ç¼–å·ã€å…¬å¸ç»´è¡¨ã€
    Supabase é…é¢å’Œ MiniMax å¥—é¤ï¼›å‰ç«¯æ ¸å¿ƒæ–‡ä»¶åœ¨æ•°æ®å¥‘çº¦ç¨³å®šåŽä¸²è¡ŒæŽ¥å…¥ã€‚

## 8. ä¸‹æ¬¡ä¼šè¯å‰çš„å¾…è¡¥ä¿¡æ¯ï¼ˆè§†ä¼šè¯ä¸»é¢˜é€‰å¸¦ï¼‰

- å¸¸å¤‡ä¸‰ä»¶å¥—ï¼šæœ¬æ–‡ä»¶ + docs/schema_snapshot.md + æœ€æ–°ä¸€ä»½ worklog
- R1 æ”¶å£ä¼šè¯ï¼šverify.sql å…¨æ®µè¾“å‡º + å„ workflow è¿è¡Œæ—¶é•¿/å¼‚å¸¸æˆªå›¾
- è´¨é‡è¯„æµ‹ä¼šè¯ï¼ˆR3ï¼‰ï¼š2â€“3 ä»½å…¸åž‹å…¬å‘Š PDFï¼ˆå•†å“/å¤–æ±‡/è¿›å±•å„ä¸€ï¼‰+ ä½ æ‰‹å·¥è®¤å®šçš„
  æ­£ç¡®æŠ½å–å€¼ï¼ˆé‡‘æ ‡å‡†é›å½¢ï¼‰
- å‰ç«¯ä¼šè¯ï¼ˆM3ï¼‰ï¼š2â€“3 ä¸ªä½ å–œæ¬¢çš„å‚è€ƒç«™æˆ–é£Žæ ¼æè¿° + æ¡Œé¢/æ‰‹æœºä½¿ç”¨æ¯”ä¾‹

## 21. M4a annual-report POC checkpoint (2026-07-20)

- Added migrations `002_periodic_reports.sql` and `003_periodic_hardening.sql`: report metadata,
  disclosure-level extraction, reported metric facts, RLS, explicit Data API grants, security-invoker
  views, and a fixed function search path. Supabase Security Advisor now reports zero findings.
- Deterministic sample: 30 A-share companies, split evenly across commodity, FX, and mixed hedging,
  with industry and ownership diversity. B-share handling is intentionally deferred after code/orgId
  mismatch was observed for 200553.
- Metadata discovery was changed from a capped full-market scan (10 minutes, only 4/30) to CNINFO
  code+orgId targeted queries (about one minute, 30/30).
- Two real PDFs were localized without LLM: JinkoSolar 289â†’15 pages and Beyondsoft 206â†’15 pages.
- One JinkoSolar report was extracted end to end in about 101 seconds: 18 reported metric facts;
  3 passed both literal-number and exact-quote checks, 15 table-derived quotes remain pending review.
- No annual-report schedule is enabled. Next gate: improve table evidence alignment, manually review the
  first two reports, then decide whether to expand from 2 to 30. See `docs/M4A_POC.md`.

## 22. M3 province and multi-year dashboard checkpoint (2026-07-21)

- Added the existing `province` dimension to event and announcement tables, detail drawers, full-result
  search, and UTF-8 CSV exports. No database migration was required because both read-only views already
  expose the company province field.
- Added a province coverage chart (Top 16 by distinct company count, with event count alongside it).
- Added one dashboard-wide year selector. It filters enterprise nature, scope, industry, province,
  approval, and field-quality charts while the year trend intentionally retains the complete time series.
- Live data verification: 2025 has 1,464 events / 1,321 companies and 1,443 rows with province; 2026 has
  1,812 events / 1,635 companies and 1,808 rows with province.
## 9. R1 checkpoint (2026-07-17)

- 2026 announcements backfill verified in the new Supabase project: 3,526 rows, covering 2026-01-01 through 2026-07-15.
- All 3,526 rows are currently `pending`; `extractions` is still empty by design.
- Next action: run `Extract Batch (LLM)` with `limit=300` for the first batch, inspect the result, then continue in batches.
## 10. R1 extraction checkpoint (2026-07-17)

- First LLM batch completed successfully: 360 extracted announcements, all with text length and PDF page evidence.
- Current queue: 360 `extracted`, 3,166 `pending`, no `failed` rows.
- Event derivation is active: 178 `hedge_events` and 360 `event_members` were rebuilt automatically.
- Continue `Extract Batch (LLM)` with `limit=300`; after pending reaches zero, run the full verification SQL and close R1.
## 11. R1 quota incident checkpoint (2026-07-17)

- Current data: 708 extracted, 2,678 pending, 139 failed, 1 skipped; 362 derived hedge events.
- The 139 failures share MiniMax HTTP 402 `insufficient_balance_error (1008)`. Pause extraction until the token plan key's available quota is confirmed.
- Recovery order: re-run probe, retry 30 failed rows, then resume 300-row batches after the small retry is stable.
## 12. M3 frontend preview checkpoint (2026-07-18)

- A real-data responsive preview is now merged under `web/`: overview metrics, event stream, announcement stream, filters, evidence drawer, quota table, and PDF links.
- The preview reads `v_ann_flow` and `v_events` with a publishable/anon key only; no service-role credential is shipped to the browser.
- GitHub Pages workflow is present in `.github/workflows/pages.yml`. Repository Pages still needs its Source set to `GitHub Actions` before the first public deployment.

## 13. M3 encoding and density fix (2026-07-18)

- Restored the frontend files as valid UTF-8 after identifying the initial GitHub connector upload transcoding issue.
- Tightened the white research-terminal layout with denser event rows, smaller masthead/metric cards, finer borders, and stronger table hierarchy while preserving mobile stacking.
- Verified the public read-only Supabase views remain available and merged the fix through PR #9.

## 14. M3 shadcn light data terminal direction (2026-07-18)

- Replaced the narrative hero and product-purpose copy with a direct real-data view titled â€œå¥—ä¿äº‹ä»¶â€.
- Adopted a shadcn/ui-inspired light system: white background, neutral colors, fine borders, small radii, compact controls, and strong information hierarchy.
- Preserved event/announcement switching, real metrics, filters, evidence drawer, and mobile layout.
- The implementation was synchronized and merged to `main` through PR #11; Pages redeployment is the remaining publication check.

## 15. R1 event rebuild primary-key fix (2026-07-18)

- `build_events.py` previously used the same `|p` suffix for every unmatched progress event under the same company/year/scope, allowing duplicate `event_key` values inside one rebuild batch.
- Unmatched progress keys now append the stable source `ann_id`; a pre-write duplicate-key guard was also added.
- The reported `PostgREST 409 / 23505` occurred after LLM extraction completed, during derived event rebuilding; no new LLM extraction is required for the already completed batch.
- Added a manual `Build Events` workflow so derived-event rebuilds can be retried without invokin×NzîÚ$z{-®éÜj×â&—6µöÖVF–÷&W÷'G6Kˆâ&—6µöÖVF–÷&W÷'E÷6÷W&6W6KŠN[ÊXZÎ[Èh©^[ÛŠŽûÉ¾XéþZx°¢&—6µöÖVF–öÆVG6Y(Â&—6µöÖVF–ö&6¶f–ÆÅ÷v–æF÷w6{º~{ºÞXú®XXŠë‚6W'f–6U÷&öÆRŠëþ™zî8 ¢æöâZûžXZÎ[ÈKŠNŠŽŠû¾Xùnh‰X©þûÈÎZûžKŠN[ÊXéþZx¾ŠŽ‹ùNY¹âCûÉµ7W&6R6V7W&—G’Gf—6÷"K‹¢Y®ŠÚn8 ¢ÒXù[ˆ>YšŽXú®Šû¾Xùn[{.ZÙŽX*Žy¨NzxiÈžX	ž˜žûÈÎKˆÞh©>XZŽih~8KˆÞ‹>yJ‚Ö–æ”ÖŽ8.Zè>Šhk.Kˆ®[ˆ.XZÎXûŽKº>zþYÞz{8¢iz^iÉþ8…EE2U$Î8y›ÞYÞXÙ^Z©.KÙ>ûÈÎKº^Xø®YÎKˆ[˜:ŽŠúÞZ(>KŠÞy¨NŠÞyIþY8ŠøÞY(Î[{.XùyIþš8î™šžŠøÞûÉ¾Šë®YÙ¾8ˆ*Y
~8¢XËþYÞiÚ^k©8ZéŽikžYùþYÞY(ÎX~Šëîh
~š8î™šžhùzK®YØ~h¹.{¹ÞXZÎ[È8 ¢ÒyÉþZéîšin‹ÚîX[j8iúR"iÚzxiÈžX	ž˜žûÉ®kþx›žyK^iË¢##RÓ"Ó#‚ikkZ®‹J.{¸þhª^˜>˜	®‹ø~[›n[Ú.h‰iÚXZÎ[È ¢Z©.KÙ>Šë[Ù^Y(ÂiÚiÚ^k©Šë[Ù^ûÉ¾XúnKˆiÚYº{Ë®[	XúþXËž˜XÞXZÎXûŽˆÎh¹.{¹Þ8.‹ùî{ºÞhš~ŠÎKŠNjÊYîK¸ÞK‹¢óûÈÀ¢[˜.zØžš¨ÎŠø˜	®‹ø~8.Šú^Šë[Ù^Xú®j~k:Ž(	ÎZ©.KÙ>hª^˜>ûÈþiÊ®jŽZéî(	ÞûÈÎKˆÞŠêXZ^jÚ>[ÈþZéŽikžjŽKè¾8 ¢ÒZ)î˜xþy¹kX¾KˆîXènXû.Y¹îZ¾YÊŽXiž[©>jŠ[ÈþYîˆz®XªŽ‹ùŠÎXZÎ[ÈXù[ˆ>YšŽûÉ´v—D‡V"W6‚K¸^hš~ŠÎkX¾Šù^ûÈÎKˆÞ‹>yJ€¢Ff–ÇžûÈÎK™þKˆÞkhŽˆ	~i	Î{J"7&VF—G>8$FVÖò[{.Z)îXªXøÎŠøhÚîzÙ¾˜ž8Xˆn[.hÈ~j~8Z©.KÙ>iÚ^k©h«Þ[žY(Î[ŠniÚ^k© ¢ZÙ~jë^y¨B55bZûÎX{®ûÈÎyIþKªrvV"öKˆî{«þKˆ®ZûÎˆŠ®k*iÈžiKžXªŽ8 ¢ÒiÊÎjÊXù[ˆ>X˜Þ‹ùÎzºþY¹î˜Yû®{«þK‹¢sC“s“vS–#C6CCVVf#&3&S#C†c363ss†f8.ˆº^ikhùKªN™Èi[NKÙ0¢i*NY¹îûÈÎ[©NK¸îŠú^Yû®{«þX‰¾[»®XøÞY	hùKªNh‰nY¹î˜XˆniJþûÈÎKˆÞ[Ë®hê‚Ö–æ8 ¢ÒXù[ˆ>X˜ÞZèÎi[NY¹î[Ù.˜	®‹ø~ûÉ£S’š’—F†öâkX¾Šù^8š8î™š’FVÖòþZé®iÉþhª^Y¢FVÖòþyIþKª~ŠêX‰.KˆîZéî™˜Rð¢jÚ>[ÈþX˜Þzºþ{¹>ièNzØ’b{¸Nzk¾{«òæöFRkX¾Šù^ûÈÎKº^Xø®yÉþZéîXZÎ[È’Y
þXªŽkX¾Šù^ûÉ¾Y
þXªŽkX¾Šù^Šû¾Xùb‚Ã#3rKŠ ¢K¨¾K»nY(Â‚ÃC“RiÚ{¹>ièNXÉnXZÎY®8#’KŠ®Xù[ˆ>ih~K»ny¨NZøn™*^XÎhš¾høþizYÞKŠÞûÈÎyIþKªrvV"öKˆÞYÊŽˆÈ>Y»NXh^8 ¢ÒKˆ¾KˆjÚ^hÈžxºÎz¸¾ŠêX‰.ZèÎh‰(	C2KŠ®yÉþZéîZéŽikžjŽKè¾{«^Y	Xˆ~x˜~ûÉ®Z©.KÙ2þ[{.yú^K¨¾K»nXøÞiú^ZéŽikžXéþih~ûÈÎŠ^›Ù ¢5¥4^855$2Kˆâ4ä”ädò˜.˜XÞYšŽûÈÎXižXZ^ZéŽikžY¹¾ŠŽ[›n˜	ZÙ~jë^Y¹îš¨Î[É^ih~ûÉ¾jÚ>[ÈþKˆ®{«þ™{Ž™zŽKùÞhÈKˆÞXùŽ8  ¢22CâXZÎY®K¨¾K»nš)Þ[ªniÚ^k©Y¹î˜KúîZHÞûÈƒ##bÓ‚Ó.ûÈ ¢ÒjžYºKˆÞYÊ‚ÄÄÞûÉ®›˜þ‹èžˆ;Þk©##bÓBÓ#’XéþŠêX‰.Y(Â##bÓrÓ’‹>š)ÞXZÎY®[{.{¸þjÚ>zîh«ÞXùnYXnY8ð¢ZInk~š)Þ[ªnûÈÎKØb##bÓrÓ#Bˆ*K‰ÎKÉ®Xk>ŠêîXú®Xiž(	ÎŠêîjŽ˜	®‹ø~(	Þ8.iz~ˆ®YŽŠxNX‰žiziÚK»n˜žhºžiÈš¹ŽZêh›¢XZÎY®KÙÎK‹®š)Þ[ªniÚ^k©ûÈÎYºjÚNK¨¾K»n[ú¾xZ~K‹®z›®ûÈÎiÉþ™™Y(Îš)Þ[ªnYÊŽX˜Þzºþi‹îzK®(	ÎiÊ®hª¾™Ë.(	Þ8 ¢ÒK¨¾K»n™‹një^Kˆîš)Þ[ªniÚ^k©xë[{.Šz>ˆ
nûÉ®™‹një^K¸ÞXùniÈš¹ŽZêh›ž[.{ª~ûÉ¾š)Þ[ªnKÉŽXXŽXùniÈš¹ŽZêh›ž[.{ª~KŠÞˆ{>[	XÈ^Y
°¢KˆiÚ™Ùîz›®K‰BÖ÷VçE÷fW&–f–VC×G'VV˜yš)Þy¨NiÈ‹ùŠêX‰.XZÎY®8.ˆ*K‰ÎKÉ®iÊ®˜xÞX‰~˜yš)Þi{nY¹î˜X‹YÎK¨¾K»`¢iÈ‹ùš)Þ[ªnXZÎY®ûÉ¾XZŽK¨¾K»nizXúþš¨ÎŠø˜yš)Þi{nh˜ÞKùÞyYžiÈš¹ŽZêh›ž[.{ª~y¨N{ªþih~iÊÎš)Þ[ªnŠÎ8 ¢ÒKúîZHÞYÎi{nh¨¢vVY(ÂV÷FU÷fW&–f–VFXižXZ^K¨¾K»nš)Þ[ªn[ú¾xZ~ûÈÎ˜þXXÞh«ÞXùn[.[{.Y¹îš¨Î8K¨¾K»nŠúnh8^XÛ@¢i‹îzK®[è^Y¹îš¨Î8.ikZ)â2KŠ®Y¹î[Ù.kX¾Šù^ûÈÎXˆnXŠ¾Šhny¹niz˜yš)Þˆ*K‰ÎKÉ®Y¹î˜8z›®˜yš)ÞŠÎKˆÞ[é~˜î‰KÞ[{.Y¹îš¨Î˜yš)Þ8¢š^zY(Î[É^ih~Y¹îš¨ÎZÙ~jë^KùÞyYž8 ¢ÒyIþKª~K¨¾K»n[.[{.XZŽ˜xþ˜xÞ[»®ûÉ£‚Ã#3rKŠ®K¨¾K»n8‚ÃC“RKŠ®h‰YŽûÈÎZÚNXKþh‰Y‚8y»ŽX[>XZÎY®iÊ®hÈ.™ÚûÉ°¢XéþXX‚CBKŠ®(	ÎK¨¾K»nš)Þ[ªnK‹®z›®KØnh‰YŽiÈžš)Þ[ªn(	Þ™zîš)Ž™˜ÞK‹¢ûÈÎš)ÞZInXùxëy¨BbKŠ®(	Îz›®˜yš)ÞŠÎ˜î‰KÞ[{ ¢Y¹îš¨Î˜yš)Þ(	Þ™zîš)ŽK™þ™˜ÞK‹¢8.k*iÈž˜xÞik‹>yJ‚ÄÄÞ8 ¢Ò›˜þ‹èžˆ;Þk©##bK¨¾K»nxëYÊŽKùÞhÈ(	Îˆ*K‰ÎZJ~KÉ®˜	®‹ø~(	ÞûÈÎš)Þ[ªniÚ^k©Y¹î˜X‹##bÓrÓ’‹>š)ÞXZÎY®ûÈÀ¢h.ZHÒ‚iÚš)Þ[ªnY(ÎiÈžiXŽiÉþ™™ûÉ®YXnY8KùÞŠø˜y2K«þXX2þYŽ{ªnK»~XÂ#K«þXX>ûÈÎZInk~KùÞŠø˜yBãRK«þXX2ð¢YŽ{ªnK»~XÂ3K«þXX>ûÈÎ{»ÎYŽKùÞŠø˜yrãRK«þXX2þYŽ{ªnK»~XÂSK«þXX>8 ¢ÒZèÎi[NY¹î[Ù.˜	®‹ø~ûÉ£c"š’—F†öâkX¾Šù^8b{¸Nzk¾{«òæöFRkX¾Šù^Y(ÎyÉþZéîXZÎ[È’Y
þXªŽkX¾Šù^ûÉ¾Y
þXª€¢kX¾Šù^Šû¾Xùb‚Ã#3rKŠ®K¨¾K»n8‚ÃC“RiÚ{¹>ièNXÉnXZÎY®8  ¢22C"âÓB##R[›N[›Nhª^jÚ>[Èþhšž˜xþûÈƒ##bÓ‚ÓŽûÈ ¢ÒzÊÎKˆ™‹një^jÚ>[ÈþXˆnjøÞY»®Zé®K‹¢†VFvUöWfVçG2ææ6†÷%÷–V#Ó##Vy¨BÃƒ"ZënXZÎXûŽ8"ÃRKŠ®K¨¾K»nûÈÀ¢[›nY»®XÉnK‹¢6öæf–röæçVÅöf÷&ÖÅó##Ræ77f8.[ú¾xZ~K‹¢Ãƒ"KŠ®YJþKˆKº>z8izz›®Kº>zûÉ¾Yî{ºÞXZÎY ¢ikZ)îKˆÞKÉ®YÊŽiÊÎ™‹një^‹ùŠÎKŠÞiKžXùŽXˆnjøÞ8 ¢ÒyÉþZéîi[hÚîj8iú^XùxëjÚ>[ÈþkKŠÞiÈ’‚Zëb"ˆ*XZÎXûŽûÈÎXúniÈ’CBZën[	®iÊ®‹ù¾XZR6ö×æ–W6K‹¾ŠŽûÉ¾KŠN{°¢XZÎXûŽYØ~[îK¨âÃƒ"ZënK¨¾K»nXˆnjøÞûÈÎKˆÞˆ;Þk+þyJŽizžiÉòô2ŠxNX‰žhé.™šN8.XX>i[hÚîXižXZ^X˜ÞKÉ®Kº^jÚ>[ÈþkYÞz{8¢ŠÎK‰®Y(ÎKÈK‰®h
~‹JŽŠ^›ÙiÈ[þXZÎXûŽK‹¾ŠŽŠë[Ù^ûÈÎkº‹k2W&–öF–5÷&W÷'G2æ6öFVZIn™JîûÈÎKˆÞKúîiKžŠŽ{¹>ièN8 ¢ÒjÚ>[Èþk[Ù>X˜ÞYû®{«þK‹®ûÉ®[{.Xùxë’Zën8[{.hùXùb‚Zën8ZK‹JRZën8[è^XùxëÃs2Zën8K«®[z^hê^Xùp¢bZën8.yIþKª~X˜ÞzºþxëiÈ’’ZënXZŽ˜:ŽKùÞyYžûÉ¾X[nKŠÒZënKˆÞ[îK¨âæ6†÷%÷–V#Ó##VjÚ>[ÈþXˆnjøÞûÈÎK¸ÞXúð¢[^zK®Y(ÎZûÎX{®ûÈÎKØnKˆÞŠêXZ^iÊÎ‹Úîhšž˜xþ‹ù¾[ªn8 ¢ÒZé®i{nkXzˆ¾KùÞhÈjøòb[þi{n‹ùŠÎûÈÎiKžK‹®(	ÎXZŽ[ˆ.YË¢##R[›N[›Nhª^XX>i[hÚîhš¾høþ[›nhÈžjÚ>[Èþk‹ø~kºB(i"Zé®KØÐ¢iÈZI¢C‚K»Ò(i"hùXùniÈZI¢‚K»Ò(i"‹é>X{®XZÎXûŽ{ª~‹ù¾[ªn(	Þ8.X˜ÞYî‹ù¾[ªnYØ~yIþh‰¥4ôâŠø®ijÞ[ú¾xZ~ûÉ¾X‰ÞZx°¢KŠNh›žz‹>Zé®K‰NK«®[z^h«Þiú^iz{;¾{¹þh
~™zîš)ŽYîûÈÎh˜ÞŠøNKËh¨®hùXùnKˆ®™™hùš¹ŽX‹#N8 ¢ÒXZŽ[ˆ.YË®XùxëKˆÞiŠþXÙ^KŠ®[›N[ªniú^Šú.ûÈÎˆÎiŠþXXŽhÈžˆz®xKnZÚ>[ªnXˆnK‹®Y¹¾KŠ®z©~Xú>ûÉ¾K»¾Kˆz©~Xú>‹ëîX‹[zŽkÚâ3šP¢Kˆ®™™K‰NK¸ÞiÈžYî{ºÞ{¹>iéÎi{nˆz®XªŽhÈžiz^iÉþK¨ÎXˆnûÈÎy»NX‹iú^Šú.ZèÎi[Nh‰n{Êžˆ{>XÙ^iz^Yîiˆîzîhª^™Iž8.Šú^KùÞhªNKúîZHÞK¨`¢izžiÉògVÆÂhš¾høþXú®Šhny¹niú^Šú.X˜Þ{È8˜xÞZHÞ‹ùŠÎK™þizk9^Š^›ÙYîjë^XZÎXûŽy¨N™zîš)Ž8 ¢ÒhùXùnYšŽKˆÞXhÞYºXÙ^K»Þhª^Y®ZK‹J^{¸ŽjÚ.i[Nh›žûÉ®ZK‹J^hª^Y®XižXZRf–ÆVF[›n{º~{ºÞKˆ¾KˆK»ÞûÉ¾iÊÎh›ž{JþŠê2K»Ð¢ZK‹J^i{nxiNijÞXšžKÙ’ÄÄÒ‹>yJŽ8KùÞyYž[{.h‰X©þ{¹>iéÎ[›nŠê’7F–öç2iˆîzîj~{ª.8&f–ÆVF{º~{ºÞKˆÞˆz®XªŽ˜xÞŠù^ûÈÀ¢h˜¾XªŽ[z^KÙÎkXikZ)îXúþ˜’&W÷'Eö–FûÈÎyJŽK¨îi‹î[Èþh.ZHÞXÙ^K»Þhª^Y®8 ¢ÒXÙ~™*.ˆ*K»Òc#ƒ.8&W÷'Eö–B##SssK¸ÞiŠþYJþKˆ[{.yú^ZK‹J^hª^Y®ûÉ¾jÚ>[ÈþXù[ˆ>YîXXŽyJŽi‹î[ÈþXZ^Xú0¢h.ZHÞ8.ˆº^XhÞjÊZK‹J^ûÈÎKùÞyYžZK‹J^x«nhY(Î™IžŠúþŠøhÚîûÈÎKˆÞ™‹¾ZîX[nKÙžjÚ>[ÈþkXZÎXûŽ8 ¢ÒKúîŠê.x˜ŽXùxëKˆÞKÉ®ˆz®XªŽ™©‰xþ[{"W‡G&7FVFh‰b&Wf–Wu÷7FGW3Ö66WFVFy¨Niz~x˜Žhª^Y®ûÉ¾Xú®iÈžiÊ®š¨ÎiK`¢iz~x˜ŽKÉ®‹ÚÎK‹¢6¶—VF8.‹ù¾[ªnKŠÞy¨NK«®[z^hê^Xù~i[hÈžŠxNˆÈ>hª^Y®XZÎXûŽXë¾˜xÞûÈÎKˆÞKÉ®YºYÎXZÎXûŽZI®KŠ®x˜ŽiÊÎ‹h^‹øp¢^8.h˜¾Xª‚&W÷'Eö–FXú®hê^Xù~XÙ^KŠ¢n(	C#KØÞi[ZÙ~ûÈÎh¹.{¹Þ˜	~Xû~Y(Â÷7Fu$U5B‹ø~kºNŠŽ‹ëî[Èþ8 ¢ÒiÊÎ‹ÚîKˆÞKúîiK’7W&6R66†VÖ8$Å>8XZÎY®kXzˆ¾h‰nX˜ÞzºþZÙ~jë^ZY{ªn8%7W&6R##b[›B'&V¶–æp¢6†ævW2j8iú^iÊ®Xùxë[ÛY8ÞxëiÈ’÷7Fu$U5BŠŽŠû¾Xižy¨NK¨¾šžûÉ¾ikŠŽ›¹ŽŠêNKˆÞi«N™Ë.y¨NXùŽi»NKˆîiÊÎ‹ÚîizX[>8 ¢ÒXù[ˆ>X˜ÞZèÎi[NY¹î[Ù.K‹¢s‚š’—F†öâkX¾Šù^8b{¸Nzk¾{«òæöFRX˜Þzºþ{¹>ièBþ˜¾‹ékX¾Šù^Y(ÎyÉþZéîXZÎ[È¢Y
þXªŽkX¾Šù^XZŽ˜:Ž˜	®‹ø~ûÉ¾yÉþZéîY
þXªŽŠû¾Xùb’Ã##KŠ®K¨¾K»nY(Â#ÃSCRiÚ{¹>ièNXÉnXZÎY®8  ¢22C2âÓBjÚ>[Èþhšž˜xþ‹ùÎzºþih~K»nZèÎi[Nh
~KúîZHÞûÈƒ##bÓ‚ÓžûÈ ¢Ò##bÓ‚Ó’x«nhZHÞjŽXùxëûÈÎjÚ>[Èþhšž˜xþXù[ˆ>Yîy¨BRjÊZé®i{nK»¾XªYØ~YÊŽŠû¾Xù`¢6öæf–röæçVÅöf÷&ÖÅó##Ræ77fi{nŠznXùUDbÓ‚Šz>z™IžŠúþûÈÎYî{ºÞXX>i[hÚîXùxë8Zé®KØÞY(ÎhùXù`¢YºX˜Þ{ÚîjÚ^šªNZK‹J^ˆÎXZŽ˜:Ž‹{>‹ø~ûÈÎi[hÚî[©>YºjÚN{º~{ºÞXÎyYžYÊ‚’Zën[^zK®XZÎXûŽ8jÚ>[ÈþkXhR‚Zën8 ¢ÒjžYºiŠþXù[ˆ>ZJ~ih~K»ni{n{¸þ‹ø~K¨niÈž‹é>X{®™[þ[ªn™™X‹ny¨NiÊÎYËKŠÞ™{N[.ûÈÎKˆÞiŠþjÚ>[ÈþkyIþh‰YšŽ8v—D‡V"7F–öç0¢h‰b7W&6Ri[hÚî™zîš)Ž8.Xù~[ÛY8Þy¨N‹ùÎzºþih~K»nXÈ^hºÎjÚ>[Èþk55n8Fö72õ$ô¤T5BæÖF8¢67&—G2öW‡G&7E÷W&–öF–5÷&W÷'G2ç–Y(ÂFW7G2÷FW7E÷W&–öF–2ç–ûÉ¾iÊÎYËZèÎi[Nih~K»nXø®Y¹î[Ù.kX¾Šù^iÊ®hÙþYØþ8 ¢ÒKúîZHÞXù[ˆ>iKžK‹®Y»®Zé®ZÙ~ˆ¨.XˆnYÙ~Šû¾XùnûÈÎYÊŽXh^ZÙŽ˜xÞ{¸B&6ScBYîy»Nhê^‹>yJ‚v—D‡V"hù.K»nX‰¾[»¢&Æö.ûÉ°¢XˆniJþi»NikX˜Þ[ø^š¾˜	ih~K»njŽZû’v—D‡V"&Æö"4„KˆîiÊÎYËv—B†6‚Öö&¦V7FûÈÎ˜þXXÞ(	ÎhùKªNh‰X©þKØnih~K»`¢Xh^ZëžKˆÞZèÎi[N(	ÞXhÞjÊXùyIþ8 ¢ÒiÊÎ‹ÚîXú®h.ZHÞ‹ùÎzºþih~K»nZèÎi[Nh
~[›nŠ^XX^iz^[ù~ûÈÎKˆÞKúîiKži[hÚî[©>{¹>ièN8[›Nhª^ZÙ~jë^ZY{ªn8jÚ>[ÈþkˆÈ>Y»N8¢jøþh›žZé®KØÒC‚K»ÞûÈþhùXùb‚K»Þy¨NXø.i[h‰nX˜Þzºþ[^zK®˜¾‹é8  ¢22CBâÓbš8î™šžjŽKè¾y¹hê~jÚ>[ÈþX˜ÞzºþKˆîŠúþhª^™{Ž™zŽûÈƒ##bÓ‚ÓûÈ ¢ÒKª~Y8Xk>zÙn‹>i[NK‹®(	ÎyÉþZéîi[hÚîizžiÉþKˆ®{«þ(	ÞûÉ®jÚ>[Èþz¹žXúþKº^YÊŽZéŽikžjŽKè¾K‹¢i{nZh.Zéî[^zK®[{.˜	®‹ø~™{Ž™zŽy¨@¢Z©.KÙ>hª^˜>ûÈþiÊ®jŽZéæŠë[Ù^8#SK»ÞZéŽikžX	ž˜ž8KŠ®jÚ>[ÈþjŽKè¾Y(ÎKˆÞKØîK¨â“R{+îzîxè~{º~{ºÞKÙÎK‹ ¢ZéŽikž˜x~™¸nzê{«þhšž˜xþyºîj~ûÈÎKˆÞXhÞKÙÎK‹®X˜ÞzºþXZ^Xú>y¨N[ÈX[>8 ¢ÒZ©.KÙ>Xù[ˆ>YšŽikZ)îXZÎXûŽ‹ª¾K»ÞKˆˆ{Nh
~8[{.XùyIþK¨¾ZéîKˆî˜xÞŠhh
~Kˆž˜xÞj
š¨ÎûÈÎ[›niJþhÈ˜xÞikŠøNKËiz.iÈžXZÎ[È ¢Šë[Ù^8#3’iÚX	ž˜žš(NkÉN{¹>iéÎK‹¢"iÚKùÞyYž83riÚhé.™šN8"iÚiz.iÈžŠúþhª^i*NY¹îûÉ¾yIþKª~XZÎ[È[.iÈ{¸ŽKùÞyY¢kþx›žyK^iË®Y(ÎK¹žK™X^[«~YBiÚûÈÎXÈ^™*"þh:zyXZÎXûŽ™Iž˜XÞKˆîxë.xù‹Úîˆ8îk9¾Xˆnié[{.j~ŠëF—6Ö—76VF8 ¢ÒikZ)â•÷&—6µ÷V&Æ–5÷&VFöæÇ’ç7ÆûÉ®XZÞ[ÊXZÎ[Èš8î™šžŠŽZû’æöæöWF†VçF–6FVFK¸^KùÞyY¢4TÄT5FûÈÆ&—6µöÖVF–öÆVG6Kˆâ&—6µöÖVF–ö&6¶f–ÆÅ÷v–æF÷w6izkXþŠxŽYšŽiØ>™™ûÉ¾XZ¾Š‚$Å0¢XZŽ˜:ŽY
þyJŽûÈÅ7W&6R6V7W&—G’Gf—6÷"K‹¢Y®ŠÚn8 ¢ÒjÚ>[Èþz¹ž[znKê~ikZ)î(	Îš8î™šžjŽKè¾y¹hê~(	ÞûÈÎYÎi{nŠû¾XùnZéŽikžY¹¾ŠŽY(ÎXZÎ[ÈZ©.KÙ>KŠNŠŽûÉ¾ZéŽikžjŽKè¾KÉŽXXŽXë¾˜xÞûÈÀ¢iJþhÈXZÎXû‚þKº>z8[›NK»Þ8š8î™šž{¾Yè¾8iÚ^k©8x«nh8ŠøhÚî[.{ª~zÙ¾˜žûÈÎš¹ŽZøn[ªnX‰~ŠŽ8Xû>Kê~iÚ^k©KˆîŠøhÚà¢Šúnh8^8UDbÓ‚55n8Xª‹ÛÒþ˜xÞŠùRþ™IžŠúþx«nhY(Îz{¾XªŽzºþ[ˆ>[8.kXþŠxŽYšŽKº>zKˆÞiú^Šú.zxiÈžZ©.KÙ>ŠŽ8 ¢ÒiÊÎYËkXþŠxŽYšŽZéîkX¾i‹îzK¢iÚZéŽikžjŽKè¾8"iÚZ©.KÙ>Šë[Ù^8"ZënXZÎXûŽûÉ³##R[›NzÙ¾˜ž{Êžˆ{2iÚûÈÀ¢Šúnh8^iÚ^k©Y(ÎiÊ®jŽZéîhùzK®jÚ>zîûÈÃ3“‚š^™Ú.izjŠ®Y	kª.X{®8.yÉþZéâ’š8î™šžY
þXªŽ{ªb"ãzy.ûÈÎK‹¾z¹žY
þXª€¢Šû¾Xùb’Ã##KŠ®K¨¾K»nY(Â#ÃSCbiÚ{¹>ièNXÉnXZÎY®8 ¢ÒY¹î[Ù.{¹>iéÎûÉ£ƒ‚š’—F†öâkX¾Šù^8r{¸Nzk¾{«òæöFRkX¾Šù^Y(Â"{¸NyÉþZéîXZÎ[È’Y
þXªŽkX¾Šù^XZŽ˜:Ž˜	®‹ø~8 ¢Kˆ¾KˆjÚ^{º~{ºÒÓfZéŽikžXéþih~{«^Y	Xˆ~x˜~ûÈÎKˆÞyJŽK‹®K¨nX˜Þzºþ[^zK®h˜¾[z^[Ù^XZ^jŽKè¾8  ¢22CRâÓfšinh›žZéŽikžš8î™šžjŽKè¾{«^Y	Xˆ~x˜~ûÈƒ##bÓ‚ÓûÈ ¢ÒikZ)îzîZé®h
~Xù[ˆ>Yš‚67&—G2÷V&Æ—6…ööff–6–Å÷&—6µö66W2ç–ûÈÎZHÞyJŽ[{.{¸þ˜x~™¸n[›nyKÖ–æ”Ö‚h«ÞXùny¨@¢[zŽkÚîZéŽikžXZÎY®ûÉ¾Xú®ZûžiÈ{¸ŽXZ^˜’DbX®KˆjÊKˆ¾‹ÛÞY(ÎXéþih~˜	ZÙ~Zé®KØÞûÈÎKˆÞ˜xÞZHÞ‹>yJ‚ÄÄÞ8.Xù[ˆ>YšŽh¹.{¹Ð¢zêynX‹n[ªn™ˆŽXÎ8X~Šëîš8î™šž8iˆîzîiÊ®XùyIþhÙþZKXø®išî˜	®k~XYhÙþZKûÈÎ[›nKº^z‹>Zé¢66Uö¶W–[˜.zØžXižXZ^8 ¢Òšinh›žjÚ>[ÈþXZ^[©22KŠ®ZéŽikžŠÞyIþY8˜xÞZJ~hÙþZKjŽKè¾ûÉ®kþx›žyK^iË®ûÈŽZéŽikžhª¾™Ë.Zéî™˜^hÙþZK‹ëîX‹˜xÞZJ~j~XxnûÈÀ¢Xéþih~iÊ®hª¾™Ë.{+îzî˜yš)ÞûÈž8‹®j:îi›®ˆ;ÞûÈƒÃ#c‚ã3’Kˆ~XX>ûÈžY(ÎZJžZè~ˆ*K»ÞûÈƒÃSC’ãƒKˆ~XX>ûÈž8.ZéŽikžY¹¾Š€¢YØ~K‹¢2ŠÎûÈó2iÚX[>{;¾ûÈó2iÚŠøhÚîûÈÎjøþKŠ®jŽKè¾ˆ{>[	K»ÞZéŽikžih~j>Y(ÂiÚ[{.˜	®‹ø~[É^ih~Kˆîi[XÎY¹îš¨Îy¨@¢š^{ª~ŠøhÚîûÉ¾{Ë®[	{+îzî˜yš)Þy¨Nkþx›žyK^iË®KùÞhÈz›®XÎûÈÎKˆÞyJŽZ©.KÙ>hª^˜>h‰njŠYè¾hêŽijÞŠ^›Ù8 ¢Òkþx›žyK^iË®Z©.KÙ>Šë[Ù^[{.‹ÚÎK‹¢öff–6–ÆÇ•ö6÷'&ö&÷&FVF[›nX[>ˆNjÚ>[ÈþjŽKè¾ûÉ¾jÚ>[ÈþX˜ÞzºþKº^ZéŽikžjŽKè¾K‹ ¢K‹¾ŠÎ8Z©.KÙ>K‹®Š^XX^iÚ^k©ûÈÎ˜þXXÞ˜xÞZHÞŠêi[8.i[hÚî[©>K¸ÞiÈ’"iÚXZÎ[ÈZ©.KÙ>Šë[Ù^ûÈÎKØnš^™Ú.YŽ[›nYî[©N[^zK ¢2KŠ®ZéŽikžjŽKè¾XªKŠ®xºÎz¸¾Z©.KÙ>{«þ{J.8 ¢ÒikZ)â&—6²öff–6–Â66W6[z^KÙÎkXûÉ®XÉ~KªÎi{n™{NjøþizR“£3Rˆz®XªŽ‹ùŠÎûÈÎ›¹ŽŠêNiÈZI®Xù[ˆ22KŠ®zÊnY€¢KŠ^jÎ™{Ž™zŽy¨NjŽKè¾ûÉ¾h˜¾XªŽXižXZ^K¸Þ™Èw&—FS×G'VVKˆâ•õTäDU%5DäFXøÎzîŠêN8.[z^KÙÎkXKˆîX[nK¹nš8î™š¢iÚ^k©X[yJ‚&—6²×6÷W&6W6[›nXù™HûÈÎ[›nKˆ®KÊKˆÞY
¾Zøn™*^y¨B¥4ôâŠø®ijÞ[ú¾xZ~8 ¢ÒyIþKª~XižXZ^YîyÉþZéîXZÎ[È’Y
þXªŽkX¾Šù^{ªb"ã"zy.ûÈÎŠû¾Xùb2KŠ®ZéŽikžjŽKè¾8"iÚZ©.KÙ>Šë[Ù^Kˆâ"KŠ®Z©.KÙ0¢iÚ^k©ûÉ¾K‹¾z¹žY
þXªŽkX¾Šù^Šû¾Xùb’Ã##KŠ®K¨¾K»nY(Â#ÃSCbiÚ{¹>ièNXÉnXZÎY®8%7W&6R6V7W&—G’Gf—6÷ ¢KùÞhÈšž8 ¢ÒZèÎi[NY¹î[Ù.K‹¢#š’—F†öâkX¾Šù^8r{¸Nzk¾{«òæöFRkX¾Šù^Y(Â"{¸NyÉþZéîXZÎ[È’Y
þXªŽkX¾Šù^XZŽ˜:Ž˜	®‹ø~8 ¢Kˆ¾Kˆ™‹një^{º~{ºÞŠ^›Ù4ä”ädþûÈþk{KªNh˜ûÈþKˆ®KªNh˜ûÈþŠøy¹KÉ®ZéŽikžiÚ^k©[›nhšžZJ~X	ž˜žh«Þj8ûÉ³SK»ÞZéŽikžX	ž˜ž8¢KŠ®jÚ>[ÈþjŽKè¾Y(ÎKˆÞKØîK¨â“RX	ž˜ž{+îzîxè~K¸ÞiŠòÓfy¨Nhšž˜xþ™{Ž™zŽ8  ¢22CbâÓfKªNi‰>h˜ZéŽikžiÚ^k©XøÎ‹ÚŽhšž[^ûÈƒ##bÓ‚ÓûÈ ¢ÒG&6²[{.YÊŽiÊÎYËZèÎh‰jÚ>[ÈþjŽKè¾Xù[ˆ>YšŽy¨NZ)î˜xþh›žjÊKúîZHÞûÉ®XXŽhé.™šN[{.{¸þZÙŽYÊŽy¨B6æ–æfó£Ææåö–CæûÈÎXhÞ[©NyJŽh›žjÊKˆ®™™ûÉ¾XZŽ˜:ŽX	ž˜žYØ~[{.Xù[ˆ>i{nKÙÎK‹®jÚ>[‹Žz›®h›žjÊ{¹>iÙþûÈÎKˆÞXhÞŠêžjøþiz^K»¾XªZK‹J^8.yIþKª~Xù[ˆ>Yîš(NŠêikZ)îXûXØîikiÙY(ÎxJnKÙÎKˆ~ik’"KŠ®[{.˜	®‹ørDbXéþih~jŽš¨Îy¨NjŽKè¾ûÈÎjÚ>[ÈþZéŽikžjŽKè¾yK2KŠ®Z)îˆ{2RKŠ®ûÉ¾iÊÎj8iú^x+žKˆÞhùX˜ÞZê>z{[{.Xiž[©>8 ¢ÒG&6²"ikZ)îk{KªNh˜ZéŽikžiÚ^k©˜.˜XÞYšŽûÈÎ[›nh¨®˜x~™¸nYšŽhšž[^K‹¢76V87§6V8ÆÆKˆžzxÞjŠ[Èþ8.Kˆ®KªNh˜{º~{ºÞKÛþyJŽZéŽikžiú^Šú.hê^Xú>ûÉ¾k{KªNh˜{¸þyÉþZéîš^™Ú.hé.iú^zîŠêNyKkXþŠxŽYšŽ‹>yJ‚ö’÷&W÷'Bõ6†÷u&W÷'BöFFûÈÎYºjÚN˜.˜XÞYšŽŠû¾XùnZéŽ{Ù¥4ôâhª^ŠŽhê^Xú>Xø®ZéŽik’DbK‹¾iË®ûÈÎˆÎKˆÞiŠþŠúþŠz>iék*iÈži[hÚîŠÎy¨N™Ùžh…DÔÂZInZ;>8 ¢ÒKªNi‰>h˜˜x~™¸nXú®Xi’&—6µ÷6÷W&6UöFö7VÖVçG6X	ž˜ž[.ûÈÎKˆÞKÉ®ˆz®XªŽX‰¾[»¢FW&—fF—fU÷&—6µö66W68.XÙ^KˆiÚ^k©ZK‹J^i{nûÈÎXúnKˆiÚ^k©y¨N[ú¾xZ~Y(Îh‰X©þXižXZ^K¸ÞŠ*¾KùÞyYžûÈÎZK‹J^jÚ>ih~j~ŠëK‹¢f–ÆVF8.jøþZJžXÉ~KªÎi{n™{B£ˆz®XªŽ‹ùŠÎiÈ‹ù3KŠ®ˆz®xKniz^y¨N˜xÞXúz©~Xú>ûÉ¾h˜¾[z^XižXZ^K¸Þ™Èw&—FS×G'VVKˆâ•õTäDU%5DäFXøÎzîŠêN8 ¢ÒiÊÎYËyÉþZéâG'’×'VîûÉ®Kˆ®KªNh˜32K»Þih~j>ûÈÃX	ž˜ž832izX[>8ZK‹J^ûÉ¾k{KªNh˜3RK»Þih~j>ûÈÃX	ž˜žûÈŽZI®k	þZI®y¹zêX{ÞûÈž83BizX[>8ZK‹J^8.jÚ>[Èþš8î™šžš^™Ú.y¨NZéŽikžih~j>Šû~k.Z)îXª7FGW3ÖW‡G&7FVFûÈÎX	ž˜žkZ)î™[þKˆÞKÉ®Š*¾kXþŠxŽYšŽi[NkŠû¾Xùn8 ¢ÒXù[ˆ>X	ž˜žš¨ÎŠøûÉ£#š’—F†öâkX¾Šù^8r{¸Nzk¾{«òæöFRkX¾Šù^XZŽ˜:Ž˜	®‹ø~ûÉ¾yÉþZéîš8î™šžš^Y
þXªŽK‹¢2KŠ®ZéŽikžjŽKè¾8"iÚZ©.KÙ>Šë[Ù^8"KŠ®Z©.KÙ>iÚ^k©ûÈÎ{ªb"ã‚zy.ûÉ¾K‹¾z¹žY
þXªŽK‹¢’Ã##KŠ®K¨¾K»nY(Â#ÃSCbiÚ{¹>ièNXÉnXZÎY®8$v—D‡V"Xù[ˆ>87F–öç2XižXZ^8RjŽKè¾yIþKª~jŽš¨Î8[˜.zØžZHÞ‹yXø¢6V7W&—G’Gf—6÷"{¹>iéÎŠë[Ù^YÊ‚Fö72÷v÷&¶Æöw2÷v÷&¶Æöuó##bÓ‚ÓÓ2æÖFûÈÎiÊ®ZèÎh‰šžKˆÞ[é~hùX˜ÞXižh‰h‰X©þ8  ¢22CrâÓB[›Nhª^ˆz®XªŽK»¾XªY	îY	KÉŽXÉnûÈƒ##bÓ‚Ó>ûÈ ¢Ò##Te’jÚ>[Èþk[Ù>X˜ÞXZÎXûŽ{ª~‹ù¾[ªnK‹®ûÉ®yºîjrÃƒ"ZënûÈÎ[{.XùxëÃscrZënûÈÎ[{.h«ÞXùb3s‚ZënûÈÎ[{.Zé®KØÞ[è^h«ÞXùbCC‚ZënûÈÎ[è^Zé®KØÒ“3‚ZënûÈÎ[è^XùxëCRZënûÉ¾XúniÈ’Zënh«ÞXùnZK‹J^Y(ÂZën™ÈŠhô5.8.yIþKª~X˜ÞzºþXÈ^Y
¾izžiÉþkZInj~iÊÎûÈÎYºˆÎ[Ù>X˜Þ[^zK®XZÎXûŽh¾i[K‹¢3ƒ’Zën8 ¢Ò‹ùŠÎŠë[Ù^zîŠêNiz~K»¾XªjøþZJžY¹¾‹ÚîYØ~z‹>Zé®h«ÞXùb‚ZënûÈÃ‚iÈ‚(	C"iz^jøþZJžYNikZ)âs"ZënûÉ¾KØnjøþ‹Úî{ªb[þi{bSXˆn™)þK‹¾Šhˆ	~YÊŽ˜xÞZHÞXZŽ[ˆ.YË®XX>i[hÚîhš¾høþûÈÎyÉþjÚ>y¨B‚ZëbÄÄÒh«ÞXùn˜	®[‹ŽXú®™È{ªb‚Xˆn™)þ8 ¢Òˆz®XªŽ‹>[ªnh¸nXˆnK‹®KŠNzxÞjŠ[ÈþûÉ®jøþZJžXÉ~KªÎi{n™{BS£#K¸^hš~ŠÎKˆjÊXZŽ[ˆ.YË¢##R[›Nhª^XX>i[hÚîhš¾høþûÉ¾XÉ~KªÎi{n™{B£C^8c£C^8#£C^8ƒ£CRy¨NY¹¾‹Úî™‰þX‰~K¸^hš~ŠÎ‹ù¾[ªn[ú¾xZ~8Zé®KØÞiÈZI¢C‚ZënY(ÎK‹.ŠÎh«ÞXùniÈZI¢3bZën8 ¢Òh˜¾[zRÖWFFFöÆö6FRöW‡G&7BXZ^Xú>86æ–æfò[›nXù™H8KˆžjÊZK‹J^xiNijÞ8XÙ^hª^Y®ZK‹J^™©Nzk¾8i‹î[ÈþZK‹J^˜xÞŠù^8ÄÄÕõD„”ä´”äsÖöfn8jÚ>[ÈþkˆÈ>Y»NY(Îi[hÚî[©>{¹>ièNYØ~KùÞhÈKˆÞXùŽ8.ynŠë®h«ÞXùnKˆ®™™yKs"ZëbþZJžhùš¹ŽX‹CBZëbþZJžûÈÎZéî™˜^Y	îY	™ÈyKXù[ˆ>Yîy¨B7F–öç2Šë[Ù^zîŠêN8 