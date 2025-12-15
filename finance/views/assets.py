from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal
from datetime import timedelta
import json
from collections import OrderedDict

from finance.models import Asset, AssetHolding, MoneySource, PortfolioSnapshot


@login_required
def assets_dashboard(request):
    # 1. Fetch Current Holdings (Standard)
    holdings = AssetHolding.objects.filter(user=request.user).select_related('asset')

    total_portfolio = Decimal("0")
    crypto_total = Decimal("0")
    stock_total = Decimal("0")

    crypto_rows = []
    stock_rows = []

    for h in holdings:
        val = h.value_eur
        total_portfolio += val
        row = {
            'id': h.id,
            'symbol': h.asset.symbol,
            'name': h.asset.name,
            'price': h.asset.current_price_eur,
            'quantity': h.quantity,
            'value': val,
        }
        if h.asset.asset_type == 'crypto':
            crypto_total += val
            crypto_rows.append(row)
        else:
            stock_total += val
            stock_rows.append(row)

    crypto_rows.sort(key=lambda x: x['value'], reverse=True)
    stock_rows.sort(key=lambda x: x['value'], reverse=True)

    # 2. PROCESS HISTORY (The 4 Timeframes)
    snapshots = PortfolioSnapshot.objects.filter(user=request.user).order_by('timestamp')

    now = timezone.now()

    # Time thresholds
    t_1h = now - timedelta(hours=1)
    t_24h = now - timedelta(hours=24)
    t_30d = now - timedelta(days=30)

    # Data Containers
    data_1h = {'labels': [], 'crypto': [], 'stock': []}
    data_24h = {'labels': [], 'crypto': [], 'stock': []}

    # For 30D and ALL, we aggregate by Day (Last snapshot of the day) to reduce noise
    daily_map_30d = OrderedDict()
    daily_map_all = OrderedDict()

    for s in snapshots:
        ts = s.timestamp
        c_val = float(s.crypto_total)
        s_val = float(s.stock_total)

        # 1H (Raw data)
        if ts >= t_1h:
            data_1h['labels'].append(ts.strftime("%H:%M"))
            data_1h['crypto'].append(c_val)
            data_1h['stock'].append(s_val)

        # 24H (Raw data)
        if ts >= t_24h:
            data_24h['labels'].append(ts.strftime("%H:%M"))
            data_24h['crypto'].append(c_val)
            data_24h['stock'].append(s_val)

        # Daily Aggregation Logic
        day_key = ts.strftime("%b %d")  # e.g. "Nov 25"

        # ALL Time
        daily_map_all[day_key] = (c_val, s_val)

        # 30 Days
        if ts >= t_30d:
            daily_map_30d[day_key] = (c_val, s_val)

    # Convert Aggregates to Lists
    def unpack_map(dmap):
        return {
            'labels': list(dmap.keys()),
            'crypto': [v[0] for v in dmap.values()],
            'stock': [v[1] for v in dmap.values()]
        }

    data_30d = unpack_map(daily_map_30d)
    data_all = unpack_map(daily_map_all)

    # Fallback for empty graphs (New user experience)
    if not data_1h['labels']:
        # Show current state as a single point
        now_str = "Now"
        for d in [data_1h, data_24h, data_30d, data_all]:
            if not d['labels']:
                d['labels'] = [now_str]
                d['crypto'] = [float(crypto_total)]
                d['stock'] = [float(stock_total)]

    ctx = {
        'total_portfolio': float(total_portfolio),
        'crypto_total': float(crypto_total),
        'stock_total': float(stock_total),
        'crypto_rows': crypto_rows,
        'stock_rows': stock_rows,

        # Pass 4 distinct JSON objects
        'json_1h': json.dumps(data_1h),
        'json_24h': json.dumps(data_24h),
        'json_30d': json.dumps(data_30d),
        'json_all': json.dumps(data_all),
    }
    return render(request, 'assets.html', ctx)

@login_required
@require_POST
def asset_add(request):
    """
    Adds a holding for an existing Asset.

    SECURITY / DATA INTEGRITY:
    - Must submit an existing Asset ID (symbol_input).
    - Must match the asset_type the form claims to be adding (crypto/stock).
    - Quantity must be a positive Decimal.
    """
    from django.utils.translation import gettext as _

    asset_id_raw = (request.POST.get('symbol_input') or '').strip()
    qty_raw = (request.POST.get('quantity', '') or '').strip().replace(',', '.')
    form_asset_type = (request.POST.get('asset_type') or '').strip()

    if not asset_id_raw:
        messages.error(request, _("Please select an asset from the list."))
        return redirect('assets_dashboard')

    if form_asset_type not in ('crypto', 'stock'):
        messages.error(request, _("Invalid asset type."))
        return redirect('assets_dashboard')

    try:
        asset_id = int(asset_id_raw)
    except (TypeError, ValueError):
        messages.error(request, _("Invalid asset selected."))
        return redirect('assets_dashboard')

    try:
        qty = Decimal(qty_raw)
    except Exception:
        messages.error(request, _("Invalid quantity."))
        return redirect('assets_dashboard')

    if qty <= 0:
        messages.error(request, _("Quantity must be greater than 0."))
        return redirect('assets_dashboard')

    try:
        asset = Asset.objects.get(id=asset_id)
    except Asset.DoesNotExist:
        messages.error(request, _("Invalid asset selected."))
        return redirect('assets_dashboard')

    if asset.asset_type != form_asset_type:
        messages.error(request, _("Invalid asset selected."))
        return redirect('assets_dashboard')

    try:
        # IMPORTANT: do NOT overwrite gettext "_" with a boolean from get_or_create
        source_name = _("Crypto Assets") if asset.asset_type == 'crypto' else _("Stock Assets")
        source, created_source = MoneySource.objects.get_or_create(
            user=request.user,
            name=source_name,
            defaults={'type': 'investment', 'is_active': True}
        )

        holding, created_holding = AssetHolding.objects.get_or_create(
            user=request.user,
            asset=asset,
            money_source=source,
            defaults={'quantity': Decimal("0")}
        )
        holding.quantity = (holding.quantity or Decimal("0")) + qty
        holding.save()

        total_val = sum(
            (h.value_eur for h in source.holdings.select_related('asset').all()),
            Decimal("0")
        )
        source.manual_balance = total_val
        source.balance_updated_at = timezone.now()
        source.save()

        messages.success(request, _("Added %(qty)s %(sym)s.") % {"qty": qty, "sym": asset.symbol})

    except Exception as e:
        messages.error(request, _("Error: %(err)s") % {"err": str(e)})

    return redirect('assets_dashboard')


@login_required
def asset_edit(request, pk):
    holding = get_object_or_404(AssetHolding, pk=pk, user=request.user)

    if request.method == "POST":
        if 'delete' in request.POST:
            holding.delete()
            messages.success(request, "Asset removed.")
            return redirect('assets_dashboard')

        qty_raw = request.POST.get('quantity').replace(',', '.')
        try:
            holding.quantity = Decimal(qty_raw)
            holding.save()
            messages.success(request, "Quantity updated.")
            return redirect('assets_dashboard')
        except:
            messages.error(request, "Invalid quantity.")

    return render(request, 'asset_edit.html', {'holding': holding})

@login_required
def api_search_asset(request):
    """
    Returns assets for dropdown search.

    Behavior:
    - If q is empty: return a default list (Top N) for that asset_type.
    - If q is provided: return matching results.
    - Optional `limit` parameter (default 50, max 200).
    """
    query = (request.GET.get('q') or '').strip()
    atype = (request.GET.get('type') or 'stock').strip()
    limit_raw = (request.GET.get('limit') or '').strip()

    if atype not in ('crypto', 'stock'):
        return JsonResponse({'results': []})

    try:
        limit = int(limit_raw) if limit_raw else 50
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 200))

    qs = Asset.objects.filter(asset_type=atype)

    # Default ordering: crypto by id (rank-ish), stocks by symbol
    if atype == 'crypto':
        qs = qs.order_by('id')
    else:
        qs = qs.order_by('symbol')

    if query:
        qs = qs.filter(Q(symbol__icontains=query) | Q(name__icontains=query))

    results_qs = qs[:limit]

    results = [{
        'symbol': a.symbol,
        'name': a.name,
        'id': a.id,
    } for a in results_qs]

    return JsonResponse({'results': results})