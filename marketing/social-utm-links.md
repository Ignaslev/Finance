# MoneyCompass social profile links

Use these exact links for the main website field on each organic social profile. Keep the names lowercase and do not shorten them, so GA4 and the MoneyCompass admin report one consistent campaign.

## Standard profile links

- Instagram: `https://www.moneycompass.lt/beta/?utm_source=instagram&utm_medium=organic_social&utm_campaign=beta_launch&utm_content=profile_bio`
- Facebook: `https://www.moneycompass.lt/beta/?utm_source=facebook&utm_medium=organic_social&utm_campaign=beta_launch&utm_content=page_link`
- TikTok: `https://www.moneycompass.lt/beta/?utm_source=tiktok&utm_medium=organic_social&utm_campaign=beta_launch&utm_content=profile_bio`

## Naming convention

- `utm_source`: platform name, such as `instagram`, `facebook`, or `tiktok`
- `utm_medium`: `organic_social` for unpaid profile and post links; `paid_social` for ads
- `utm_campaign`: stable campaign name, currently `beta_launch`
- `utm_content`: placement or creative name, such as `profile_bio`, `page_link`, `video_budget_hook_v1`
- `utm_term`: optional audience/ad-set label for paid campaigns

For paid Meta ads, use `utm_source={{site_source_name}}&utm_medium=paid_social&utm_campaign={{campaign.name}}&utm_content={{ad.name}}&utm_term={{adset.name}}` in Meta's URL parameters field.
