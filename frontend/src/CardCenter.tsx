import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { Account, Asset, CardCost, CardRecord, Category } from "./api";
import { addDecimal, divideDecimal, isPositiveDecimal } from "./decimal";
import { formatMyr, localDateTimeValue } from "./format";

type CardMode = "OVERVIEW" | "AUTHORIZE" | "SETTLE" | "REFUND" | "REWARD";

type Props = {
  assets: Asset[];
  accounts: Account[];
  categories: Category[];
  cards: CardRecord[];
  costs: CardCost[];
  busy: boolean;
  onAuthorize: (payload: Record<string, unknown>) => Promise<boolean>;
  onReverseAuthorization: (id: string) => Promise<boolean>;
  onSettle: (payload: Record<string, unknown>) => Promise<boolean>;
  onRefund: (id: string, payload: Record<string, unknown>) => Promise<boolean>;
  onReward: (id: string, payload: Record<string, unknown>) => Promise<boolean>;
  onCreditReward: (
    id: string,
    payload: Record<string, unknown>,
  ) => Promise<boolean>;
};

type SettlementDraft = {
  authorization_id: string;
  provider: string;
  provider_account_id: string;
  external_id: string;
  card_account_id: string;
  merchant_name: string;
  merchant_country: string;
  merchant_asset_id: string;
  merchant_amount: string;
  billing_asset_id: string;
  billing_amount: string;
  merchant_value_myr: string;
  reference_fx_rate: string;
  expense_account_id: string;
  category_id: string;
  gain_loss_account_id: string;
  settled_at: string;
};

type FundingLegDraft = {
  account_id: string;
  asset_id: string;
  quantity: string;
  transaction_value_myr: string;
  reference_value_myr: string;
};

type FeeDraft = {
  component_type: string;
  asset_id: string;
  amount: string;
  value_myr: string;
  expense_account_id: string;
  funding_account_id: string;
  included_in_funding_amount: boolean;
};

type RefundLegDraft = {
  account_id: string;
  asset_id: string;
  quantity: string;
  transaction_value_myr: string;
  reference_value_myr: string;
};

function emptySettlement(): SettlementDraft {
  return {
    authorization_id: "",
    provider: "",
    provider_account_id: "",
    external_id: "",
    card_account_id: "",
    merchant_name: "",
    merchant_country: "",
    merchant_asset_id: "",
    merchant_amount: "",
    billing_asset_id: "",
    billing_amount: "",
    merchant_value_myr: "",
    reference_fx_rate: "",
    expense_account_id: "",
    category_id: "",
    gain_loss_account_id: "",
    settled_at: localDateTimeValue(),
  };
}

function emptyFundingLeg(): FundingLegDraft {
  return {
    account_id: "",
    asset_id: "",
    quantity: "",
    transaction_value_myr: "",
    reference_value_myr: "",
  };
}

function emptyFee(): FeeDraft {
  return {
    component_type: "CARD_FEE",
    asset_id: "",
    amount: "",
    value_myr: "",
    expense_account_id: "",
    funding_account_id: "",
    included_in_funding_amount: false,
  };
}

function emptyRefundLeg(): RefundLegDraft {
  return {
    account_id: "",
    asset_id: "",
    quantity: "",
    transaction_value_myr: "",
    reference_value_myr: "",
  };
}

function values(form: HTMLFormElement) {
  const data = new FormData(form);
  return (key: string) => String(data.get(key) ?? "");
}

function resetSubmittedForm(form: HTMLFormElement, dateField: string) {
  form.reset();
  const dateInput = form.elements.namedItem(dateField);
  if (dateInput instanceof HTMLInputElement)
    dateInput.value = localDateTimeValue();
}

function assetOptions(assets: Asset[]) {
  return assets.map((asset) => (
    <option value={asset.id} key={asset.id}>
      {asset.symbol} · {asset.name}
    </option>
  ));
}

function accountOptions(accounts: Account[], type: string) {
  return accounts
    .filter((account) => account.account_type === type)
    .map((account) => (
      <option value={account.id} key={account.id}>
        {account.name}
      </option>
    ));
}

function categoryOptions(categories: Category[], kind: Category["kind"]) {
  return categories
    .filter((category) => category.active && category.kind === kind)
    .map((category) => (
      <option value={category.id} key={category.id}>
        {category.name}
      </option>
    ));
}

function sumDecimal(valuesToAdd: string[]) {
  return valuesToAdd.reduce((total, value) => {
    if (!value) return total;
    try {
      return addDecimal(total, value);
    } catch {
      return total;
    }
  }, "0");
}

function decimalGreater(left: string, right: string) {
  try {
    return isPositiveDecimal(addDecimal(left, `-${right}`));
  } catch {
    return false;
  }
}

function derivedRate(value: string, quantity: string) {
  if (!isPositiveDecimal(value) || !isPositiveDecimal(quantity)) return "";
  try {
    return divideDecimal(value, quantity, 18);
  } catch {
    return "";
  }
}

export default function CardCenter(props: Props) {
  const [mode, setMode] = useState<CardMode>("OVERVIEW");
  return (
    <div className="stack">
      <section className="panel card-center">
        <div className="mode-tabs card-tabs">
          {(
            ["OVERVIEW", "AUTHORIZE", "SETTLE", "REFUND", "REWARD"] as const
          ).map((item) => (
            <button
              type="button"
              className={mode === item ? "active" : ""}
              onClick={() => setMode(item)}
              key={item}
            >
              {item}
            </button>
          ))}
        </div>
        {mode === "OVERVIEW" && <CardOverview {...props} />}
        {mode === "AUTHORIZE" && <AuthorizationForm {...props} />}
        {mode === "SETTLE" && <SettlementForm {...props} />}
        {mode === "REFUND" && <RefundForm {...props} />}
        {mode === "REWARD" && <RewardForms {...props} />}
      </section>
    </div>
  );
}

function CardOverview({
  cards,
  costs,
  assets,
  onReverseAuthorization,
  busy,
}: Props) {
  const assetSymbols = Object.fromEntries(
    assets.map((asset) => [asset.id, asset.symbol]),
  );
  return (
    <>
      <div className="section-title">
        <div>
          <span className="eyebrow">SETTLED ECONOMICS</span>
          <h2>Card cost waterfall</h2>
        </div>
        <span className="count">{costs.length}</span>
      </div>
      <div className="card-cost-grid">
        {costs.map((cost) => (
          <article className="card-cost" key={cost.id}>
            <div className="card-cost-head">
              <div>
                <span>{cost.provider}</span>
                <h3>{cost.merchant_name}</h3>
              </div>
              <span className={`pill ${cost.status.toLowerCase()}`}>
                {cost.status}
              </span>
            </div>
            <div className="waterfall">
              <div>
                <span>Merchant value</span>
                <strong>{formatMyr(cost.merchant_value_myr)}</strong>
              </div>
              <div>
                <span>Funding reference</span>
                <strong>{formatMyr(cost.funding_value_myr)}</strong>
              </div>
              {cost.fees.map((fee) => (
                <div key={fee.component_type}>
                  <span>{fee.component_type.replaceAll("_", " ")}</span>
                  <strong>{formatMyr(fee.value_myr)}</strong>
                </div>
              ))}
              {cost.fx_deviation_myr !== null && (
                <div>
                  <span>FX deviation</span>
                  <strong>{formatMyr(cost.fx_deviation_myr)}</strong>
                </div>
              )}
              {cost.conversion_deviation_myr !== null && (
                <div>
                  <span>Conversion deviation</span>
                  <strong>{formatMyr(cost.conversion_deviation_myr)}</strong>
                </div>
              )}
              {cost.refunded_value_myr !== "0" && (
                <div className="offset">
                  <span>Refunded assets</span>
                  <strong>− {formatMyr(cost.refunded_value_myr)}</strong>
                </div>
              )}
              {cost.credited_cashback_value_myr !== "0" && (
                <div className="offset">
                  <span>Credited cashback</span>
                  <strong>
                    − {formatMyr(cost.credited_cashback_value_myr)}
                  </strong>
                </div>
              )}
              <div className="total">
                <span>Net economic cost</span>
                <strong>{formatMyr(cost.net_economic_cost_myr)}</strong>
              </div>
            </div>
            <div className="funding-tags">
              {cost.funding_legs.map((leg) => (
                <span key={`${leg.asset_id}-${leg.quantity}`}>
                  {leg.quantity} {leg.asset_symbol}
                </span>
              ))}
            </div>
            <small>
              {cost.breakdown_confidence} breakdown ·{" "}
              {new Date(cost.settled_at).toLocaleDateString()}
            </small>
          </article>
        ))}
        {!costs.length && (
          <div className="empty">
            Settled purchases will show their cost breakdown here.
          </div>
        )}
      </div>
      <div className="section-title card-history-title">
        <div>
          <span className="eyebrow">EXTERNAL STATE</span>
          <h2>Authorizations, captures and refunds</h2>
        </div>
      </div>
      <div className="table-wrap card-history">
        <table>
          <thead>
            <tr>
              <th>Provider</th>
              <th>Type</th>
              <th>Merchant</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Hold / action</th>
            </tr>
          </thead>
          <tbody>
            {cards.map((card) => (
              <tr key={card.id}>
                <td>{card.provider}</td>
                <td>{card.transaction_type}</td>
                <td>{card.merchant_name}</td>
                <td>
                  {card.merchant_amount}{" "}
                  {assetSymbols[card.merchant_asset_id] ?? ""}
                </td>
                <td>
                  <span className={`pill ${card.status.toLowerCase()}`}>
                    {card.status}
                  </span>
                </td>
                <td>
                  {card.status === "AUTHORIZED" ? (
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() => void onReverseAuthorization(card.id)}
                    >
                      Reverse hold
                    </button>
                  ) : (
                    (card.hold?.status ?? "—")
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function AuthorizationForm({ assets, accounts, busy, onAuthorize }: Props) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const value = values(form);
    const succeeded = await onAuthorize({
      provider: value("provider"),
      provider_account_id: value("provider_account_id"),
      external_id: value("external_id") || null,
      card_account_id: value("card_account_id"),
      merchant_name: value("merchant_name"),
      merchant_country: value("merchant_country") || null,
      merchant_asset_id: value("merchant_asset_id"),
      merchant_amount: value("merchant_amount"),
      billing_asset_id: value("billing_asset_id"),
      billing_amount: value("billing_amount"),
      merchant_value_myr: value("merchant_value_myr"),
      hold_account_id: value("hold_account_id"),
      hold_asset_id: value("hold_asset_id"),
      hold_amount: value("hold_amount"),
      hold_value_myr: value("hold_value_myr"),
      authorized_at: new Date(value("authorized_at")).toISOString(),
    });
    if (succeeded) resetSubmittedForm(form, "authorized_at");
  }
  return (
    <>
      <div className="section-title">
        <div>
          <span className="eyebrow">NO LEDGER ENTRY</span>
          <h2>Record authorization hold</h2>
        </div>
      </div>
      <p className="form-intro">
        Authorization reduces available balance only. Settlement later creates
        the expense and FIFO disposal.
      </p>
      <form onSubmit={(event) => void submit(event)}>
        <label>
          Provider
          <input name="provider" placeholder="Bybit" required />
        </label>
        <label>
          Provider account ID
          <input name="provider_account_id" required />
        </label>
        <label>
          External ID
          <input name="external_id" />
        </label>
        <label>
          Authorized at
          <input
            name="authorized_at"
            type="datetime-local"
            defaultValue={localDateTimeValue()}
            required
          />
        </label>
        <label>
          Card account
          <select name="card_account_id" required>
            <option value="">Select</option>
            {accountOptions(accounts, "ASSET")}
          </select>
        </label>
        <label>
          Merchant
          <input name="merchant_name" required />
        </label>
        <label>
          Merchant country
          <input name="merchant_country" maxLength={2} placeholder="MY" />
        </label>
        <label>
          Merchant asset
          <select name="merchant_asset_id" required>
            <option value="">Select</option>
            {assetOptions(assets)}
          </select>
        </label>
        <label>
          Merchant amount
          <input name="merchant_amount" inputMode="decimal" required />
        </label>
        <label>
          Merchant value MYR
          <input name="merchant_value_myr" inputMode="decimal" required />
        </label>
        <label>
          Billing asset
          <select name="billing_asset_id" required>
            <option value="">Select</option>
            {assetOptions(assets)}
          </select>
        </label>
        <label>
          Billing amount
          <input name="billing_amount" inputMode="decimal" required />
        </label>
        <label>
          Hold account
          <select name="hold_account_id" required>
            <option value="">Select</option>
            {accountOptions(accounts, "ASSET")}
          </select>
        </label>
        <label>
          Hold asset
          <select name="hold_asset_id" required>
            <option value="">Select</option>
            {assetOptions(assets)}
          </select>
        </label>
        <label>
          Hold quantity
          <input name="hold_amount" inputMode="decimal" required />
        </label>
        <label>
          Hold value MYR
          <input name="hold_value_myr" inputMode="decimal" required />
        </label>
        <div className="wide form-actions">
          <button className="primary" disabled={busy}>
            Create hold
          </button>
        </div>
      </form>
    </>
  );
}

function SettlementForm({
  assets,
  accounts,
  categories,
  cards,
  busy,
  onSettle,
}: Props) {
  const authorizations = cards.filter(
    (card) =>
      card.transaction_type === "AUTHORIZATION" && card.status === "AUTHORIZED",
  );
  const [draft, setDraft] = useState<SettlementDraft>(() => emptySettlement());
  const [fundingLegs, setFundingLegs] = useState<FundingLegDraft[]>([
    emptyFundingLeg(),
  ]);
  const [fees, setFees] = useState<FeeDraft[]>([]);
  const authorization = authorizations.find(
    (card) => card.id === draft.authorization_id,
  );
  const linked = Boolean(authorization);
  const fundingTotal = sumDecimal(
    fundingLegs.map((leg) => leg.transaction_value_myr),
  );
  const includedFeeTotal = sumDecimal(
    fees
      .filter((fee) => fee.included_in_funding_amount)
      .map((fee) => fee.value_myr),
  );
  const expectedFundingTotal = sumDecimal([
    draft.merchant_value_myr,
    includedFeeTotal,
  ]);
  const fundingMatches =
    isPositiveDecimal(draft.merchant_value_myr) &&
    fundingTotal === expectedFundingTotal;
  const fundingComplete = fundingLegs.every(
    (leg) =>
      leg.account_id &&
      leg.asset_id &&
      isPositiveDecimal(leg.quantity) &&
      isPositiveDecimal(leg.transaction_value_myr) &&
      isPositiveDecimal(leg.reference_value_myr),
  );
  const feesComplete = fees.every(
    (fee) =>
      fee.component_type &&
      fee.asset_id &&
      isPositiveDecimal(fee.amount) &&
      isPositiveDecimal(fee.value_myr) &&
      fee.expense_account_id &&
      (fee.included_in_funding_amount || fee.funding_account_id),
  );

  function updateDraft(field: keyof SettlementDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  function selectAuthorization(id: string) {
    const selected = authorizations.find((card) => card.id === id);
    if (!selected) {
      setDraft((current) => ({
        ...emptySettlement(),
        settled_at: current.settled_at,
      }));
      return;
    }
    setDraft((current) => ({
      ...current,
      authorization_id: selected.id,
      provider: selected.provider,
      provider_account_id: selected.provider_account_id,
      card_account_id: selected.card_account_id,
      merchant_name: selected.merchant_name,
      merchant_country: selected.merchant_country ?? "",
      merchant_asset_id: selected.merchant_asset_id,
      merchant_amount: selected.merchant_amount,
      billing_asset_id: selected.billing_asset_id,
      billing_amount: selected.billing_amount,
      merchant_value_myr: selected.merchant_value_myr,
    }));
  }

  function updateFunding(
    index: number,
    field: keyof FundingLegDraft,
    value: string,
  ) {
    setFundingLegs((current) =>
      current.map((leg, rowIndex) =>
        rowIndex === index ? { ...leg, [field]: value } : leg,
      ),
    );
  }

  function updateFee(
    index: number,
    field: keyof FeeDraft,
    value: string | boolean,
  ) {
    setFees((current) =>
      current.map((fee, rowIndex) =>
        rowIndex === index ? { ...fee, [field]: value } : fee,
      ),
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (
      !form.reportValidity() ||
      !fundingMatches ||
      !fundingComplete ||
      !feesComplete
    )
      return;
    const succeeded = await onSettle({
      authorization_id: draft.authorization_id || null,
      provider: draft.provider,
      provider_account_id: draft.provider_account_id,
      external_id: draft.external_id || null,
      card_account_id: draft.card_account_id,
      merchant_name: draft.merchant_name,
      merchant_country: draft.merchant_country || null,
      merchant_asset_id: draft.merchant_asset_id,
      merchant_amount: draft.merchant_amount,
      billing_asset_id: draft.billing_asset_id,
      billing_amount: draft.billing_amount,
      merchant_value_myr: draft.merchant_value_myr,
      reference_fx_rate: draft.reference_fx_rate || null,
      expense_account_id: draft.expense_account_id,
      category_id: draft.category_id,
      gain_loss_account_id: draft.gain_loss_account_id,
      settled_at: new Date(draft.settled_at).toISOString(),
      final_capture: true,
      funding_legs: fundingLegs.map((leg) => ({
        account_id: leg.account_id,
        asset_id: leg.asset_id,
        quantity: leg.quantity,
        transaction_value_myr: leg.transaction_value_myr,
        reference_value_myr: leg.reference_value_myr,
        actual_conversion_rate:
          derivedRate(leg.transaction_value_myr, leg.quantity) || null,
      })),
      fees: fees.map((fee) => ({
        component_type: fee.component_type,
        asset_id: fee.asset_id,
        amount: fee.amount,
        value_myr: fee.value_myr,
        accounting_treatment: "EXPENSED",
        included_in_funding_amount: fee.included_in_funding_amount,
        expense_account_id: fee.expense_account_id,
        funding_account_id: fee.included_in_funding_amount
          ? null
          : fee.funding_account_id,
      })),
    });
    if (succeeded) {
      setDraft(emptySettlement());
      setFundingLegs([emptyFundingLeg()]);
      setFees([]);
    }
  }

  return (
    <>
      <div className="section-title">
        <div>
          <span className="eyebrow">POSTED CARD EVENT</span>
          <h2>Settle card purchase</h2>
        </div>
      </div>
      <p className="form-intro">
        Linked settlements use one final capture. Add every funding asset and
        fee row before posting; the totals must balance.
      </p>
      <form onSubmit={(event) => void submit(event)}>
        <label>
          Authorization
          <select
            aria-label="Authorization"
            value={draft.authorization_id}
            onChange={(event) => selectAuthorization(event.target.value)}
          >
            <option value="">Manual settlement</option>
            {authorizations.map((card) => (
              <option value={card.id} key={card.id}>
                {card.provider} · {card.merchant_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Settled at
          <input
            aria-label="Settled at"
            type="datetime-local"
            value={draft.settled_at}
            onChange={(event) => updateDraft("settled_at", event.target.value)}
            required
          />
        </label>
        <fieldset
          className="wide identity-summary"
          key={draft.authorization_id || "manual"}
        >
          <legend>
            {linked ? "Linked authorization identity" : "Settlement identity"}
          </legend>
          <label>
            Provider
            <input
              aria-label="Provider"
              value={draft.provider}
              onChange={(event) => updateDraft("provider", event.target.value)}
              readOnly={linked}
              required
            />
          </label>
          <label>
            Provider account ID
            <input
              aria-label="Provider account ID"
              value={draft.provider_account_id}
              onChange={(event) =>
                updateDraft("provider_account_id", event.target.value)
              }
              readOnly={linked}
              required
            />
          </label>
          <label>
            Settlement external ID
            <input
              aria-label="Settlement external ID"
              value={draft.external_id}
              onChange={(event) =>
                updateDraft("external_id", event.target.value)
              }
            />
          </label>
          <label>
            Card account
            <select
              aria-label="Card account"
              value={draft.card_account_id}
              onChange={(event) =>
                updateDraft("card_account_id", event.target.value)
              }
              disabled={linked}
              required
            >
              <option value="">Select</option>
              {accountOptions(accounts, "ASSET")}
            </select>
          </label>
          <label>
            Merchant
            <input
              aria-label="Merchant"
              value={draft.merchant_name}
              onChange={(event) =>
                updateDraft("merchant_name", event.target.value)
              }
              readOnly={linked}
              required
            />
          </label>
          <label>
            Country
            <input
              aria-label="Country"
              value={draft.merchant_country}
              onChange={(event) =>
                updateDraft("merchant_country", event.target.value)
              }
              readOnly={linked}
              maxLength={2}
            />
          </label>
          <label>
            Merchant asset
            <select
              aria-label="Merchant asset"
              value={draft.merchant_asset_id}
              onChange={(event) =>
                updateDraft("merchant_asset_id", event.target.value)
              }
              disabled={linked}
              required
            >
              <option value="">Select</option>
              {assetOptions(assets)}
            </select>
          </label>
          <label>
            Billing asset
            <select
              aria-label="Billing asset"
              value={draft.billing_asset_id}
              onChange={(event) =>
                updateDraft("billing_asset_id", event.target.value)
              }
              disabled={linked}
              required
            >
              <option value="">Select</option>
              {assetOptions(assets)}
            </select>
          </label>
        </fieldset>
        <label>
          Merchant amount
          <input
            aria-label="Merchant amount"
            inputMode="decimal"
            value={draft.merchant_amount}
            onChange={(event) =>
              updateDraft("merchant_amount", event.target.value)
            }
            required
          />
        </label>
        <label>
          Billing amount
          <input
            aria-label="Billing amount"
            inputMode="decimal"
            value={draft.billing_amount}
            onChange={(event) =>
              updateDraft("billing_amount", event.target.value)
            }
            required
          />
        </label>
        <label>
          Merchant value MYR
          <input
            aria-label="Merchant value MYR"
            inputMode="decimal"
            value={draft.merchant_value_myr}
            onChange={(event) =>
              updateDraft("merchant_value_myr", event.target.value)
            }
            required
          />
        </label>
        <label>
          Reference FX rate
          <input
            aria-label="Reference FX rate"
            inputMode="decimal"
            value={draft.reference_fx_rate}
            onChange={(event) =>
              updateDraft("reference_fx_rate", event.target.value)
            }
          />
          <small>merchant asset / billing asset</small>
        </label>
        <label>
          Expense account
          <select
            aria-label="Expense account"
            value={draft.expense_account_id}
            onChange={(event) =>
              updateDraft("expense_account_id", event.target.value)
            }
            required
          >
            <option value="">Select</option>
            {accountOptions(accounts, "EXPENSE")}
          </select>
        </label>
        <label>
          Category
          <select
            aria-label="Category"
            value={draft.category_id}
            onChange={(event) => updateDraft("category_id", event.target.value)}
            required
          >
            <option value="">Select</option>
            {categoryOptions(categories, "EXPENSE")}
          </select>
        </label>
        <label>
          Gain/loss account
          <select
            aria-label="Gain/loss account"
            value={draft.gain_loss_account_id}
            onChange={(event) =>
              updateDraft("gain_loss_account_id", event.target.value)
            }
            required
          >
            <option value="">Select</option>
            {accountOptions(accounts, "GAIN_LOSS")}
          </select>
        </label>

        <fieldset className="wide fee-fields line-items">
          <legend>Funding legs</legend>
          {fundingLegs.map((leg, index) => (
            <div className="line-item" key={index}>
              <label>
                Funding account {index + 1}
                <select
                  value={leg.account_id}
                  onChange={(event) =>
                    updateFunding(index, "account_id", event.target.value)
                  }
                  required
                >
                  <option value="">Select</option>
                  {accountOptions(accounts, "ASSET")}
                </select>
              </label>
              <label>
                Funding asset {index + 1}
                <select
                  value={leg.asset_id}
                  onChange={(event) =>
                    updateFunding(index, "asset_id", event.target.value)
                  }
                  required
                >
                  <option value="">Select</option>
                  {assetOptions(assets)}
                </select>
              </label>
              <label>
                Funding quantity {index + 1}
                <input
                  inputMode="decimal"
                  value={leg.quantity}
                  onChange={(event) =>
                    updateFunding(index, "quantity", event.target.value)
                  }
                  required
                />
              </label>
              <label>
                Funding transaction value {index + 1}
                <input
                  inputMode="decimal"
                  value={leg.transaction_value_myr}
                  onChange={(event) =>
                    updateFunding(
                      index,
                      "transaction_value_myr",
                      event.target.value,
                    )
                  }
                  required
                />
              </label>
              <label>
                Funding reference value {index + 1}
                <input
                  inputMode="decimal"
                  value={leg.reference_value_myr}
                  onChange={(event) =>
                    updateFunding(
                      index,
                      "reference_value_myr",
                      event.target.value,
                    )
                  }
                  required
                />
              </label>
              <label>
                Derived conversion rate {index + 1}
                <input
                  value={derivedRate(leg.transaction_value_myr, leg.quantity)}
                  readOnly
                />
              </label>
              {fundingLegs.length > 1 && (
                <button
                  className="text-button row-remove"
                  type="button"
                  onClick={() =>
                    setFundingLegs((current) =>
                      current.filter((_item, rowIndex) => rowIndex !== index),
                    )
                  }
                >
                  Remove leg
                </button>
              )}
            </div>
          ))}
          <div className="row-actions">
            <button
              className="text-button"
              type="button"
              onClick={() =>
                setFundingLegs((current) => [...current, emptyFundingLeg()])
              }
            >
              Add funding leg
            </button>
          </div>
        </fieldset>
        <div className="wide form-summary" role="status">
          <span>
            Funding transaction total: <strong>{fundingTotal}</strong>
          </span>
          <span>
            Required total: <strong>{expectedFundingTotal}</strong>
          </span>
          {!fundingMatches && (
            <span className="field-error">
              Funding total must equal merchant value plus included fees.
            </span>
          )}
        </div>

        <fieldset className="wide fee-fields line-items">
          <legend>Fees</legend>
          {!fees.length && <p className="empty">No explicit fees added.</p>}
          {fees.map((fee, index) => (
            <div className="line-item" key={index}>
              <label>
                Fee type {index + 1}
                <input
                  value={fee.component_type}
                  onChange={(event) =>
                    updateFee(index, "component_type", event.target.value)
                  }
                  required
                />
              </label>
              <label>
                Fee asset {index + 1}
                <select
                  value={fee.asset_id}
                  onChange={(event) =>
                    updateFee(index, "asset_id", event.target.value)
                  }
                  required
                >
                  <option value="">Select</option>
                  {assetOptions(assets)}
                </select>
              </label>
              <label>
                Fee quantity {index + 1}
                <input
                  inputMode="decimal"
                  value={fee.amount}
                  onChange={(event) =>
                    updateFee(index, "amount", event.target.value)
                  }
                  required
                />
              </label>
              <label>
                Fee value MYR {index + 1}
                <input
                  inputMode="decimal"
                  value={fee.value_myr}
                  onChange={(event) =>
                    updateFee(index, "value_myr", event.target.value)
                  }
                  required
                />
              </label>
              <label>
                Fee expense account {index + 1}
                <select
                  value={fee.expense_account_id}
                  onChange={(event) =>
                    updateFee(index, "expense_account_id", event.target.value)
                  }
                  required
                >
                  <option value="">Select</option>
                  {accountOptions(accounts, "EXPENSE")}
                </select>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={fee.included_in_funding_amount}
                  onChange={(event) =>
                    updateFee(
                      index,
                      "included_in_funding_amount",
                      event.target.checked,
                    )
                  }
                />{" "}
                Included in funding amount
              </label>
              {!fee.included_in_funding_amount && (
                <label>
                  Fee funding account {index + 1}
                  <select
                    value={fee.funding_account_id}
                    onChange={(event) =>
                      updateFee(index, "funding_account_id", event.target.value)
                    }
                    required
                  >
                    <option value="">Select</option>
                    {accountOptions(accounts, "ASSET")}
                  </select>
                </label>
              )}
              <button
                className="text-button row-remove"
                type="button"
                onClick={() =>
                  setFees((current) =>
                    current.filter((_item, rowIndex) => rowIndex !== index),
                  )
                }
              >
                Remove fee
              </button>
            </div>
          ))}
          <div className="row-actions">
            <button
              className="text-button"
              type="button"
              onClick={() => setFees((current) => [...current, emptyFee()])}
            >
              Add fee
            </button>
          </div>
        </fieldset>
        <div className="wide form-actions">
          <button
            className="primary"
            disabled={
              busy || !fundingMatches || !fundingComplete || !feesComplete
            }
          >
            Post settlement
          </button>
        </div>
      </form>
    </>
  );
}

function RefundForm({
  assets,
  accounts,
  categories,
  cards,
  busy,
  onRefund,
}: Props) {
  const purchases = cards.filter(
    (card) =>
      card.transaction_type === "PURCHASE" &&
      card.refundable_remaining_myr !== null &&
      isPositiveDecimal(card.refundable_remaining_myr),
  );
  const [cardId, setCardId] = useState("");
  const [externalId, setExternalId] = useState("");
  const [refundedAt, setRefundedAt] = useState(localDateTimeValue());
  const [description, setDescription] = useState("");
  const [legs, setLegs] = useState<RefundLegDraft[]>([emptyRefundLeg()]);
  const purchase = purchases.find((card) => card.id === cardId);
  const expenseAccount = purchase?.expense_account_id
    ? accounts.find((account) => account.id === purchase.expense_account_id)
    : undefined;
  const category = purchase?.category_id
    ? categories.find((item) => item.id === purchase.category_id)
    : undefined;
  const transactionTotal = sumDecimal(
    legs.map((leg) => leg.transaction_value_myr),
  );
  const referenceTotal = sumDecimal(legs.map((leg) => leg.reference_value_myr));
  const overage = Boolean(
    purchase &&
    decimalGreater(transactionTotal, purchase.refundable_remaining_myr ?? "0"),
  );
  const legsComplete = legs.every(
    (leg) =>
      leg.account_id &&
      leg.asset_id &&
      isPositiveDecimal(leg.quantity) &&
      isPositiveDecimal(leg.transaction_value_myr) &&
      isPositiveDecimal(leg.reference_value_myr),
  );

  function updateLeg(
    index: number,
    field: keyof RefundLegDraft,
    value: string,
  ) {
    setLegs((current) =>
      current.map((leg, rowIndex) =>
        rowIndex === index ? { ...leg, [field]: value } : leg,
      ),
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !purchase ||
      !expenseAccount ||
      overage ||
      !legsComplete ||
      !event.currentTarget.reportValidity()
    )
      return;
    const succeeded = await onRefund(purchase.id, {
      external_id: externalId || null,
      refunded_at: new Date(refundedAt).toISOString(),
      description,
      refund_legs: legs,
    });
    if (succeeded) {
      setCardId("");
      setExternalId("");
      setRefundedAt(localDateTimeValue());
      setDescription("");
      setLegs([emptyRefundLeg()]);
    }
  }

  return (
    <>
      <div className="section-title">
        <div>
          <span className="eyebrow">NEW REVERSING FACT</span>
          <h2>Record actual refund</h2>
        </div>
      </div>
      <p className="form-intro">
        The server derives the refund total, original expense account and
        purchase status. Each returned asset creates a new cost lot.
      </p>
      <form onSubmit={(event) => void submit(event)}>
        <label>
          Purchase
          <select
            aria-label="Purchase"
            value={cardId}
            onChange={(event) => setCardId(event.target.value)}
            required
          >
            <option value="">Select</option>
            {purchases.map((card) => (
              <option value={card.id} key={card.id}>
                {card.merchant_name} · {formatMyr(card.merchant_value_myr)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Refunded at
          <input
            aria-label="Refunded at"
            type="datetime-local"
            value={refundedAt}
            onChange={(event) => setRefundedAt(event.target.value)}
            required
          />
        </label>
        <label>
          External ID
          <input
            aria-label="External ID"
            value={externalId}
            onChange={(event) => setExternalId(event.target.value)}
          />
        </label>
        <label>
          Description
          <input
            aria-label="Description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <div className="wide identity-summary">
          <span>
            Original expense account:{" "}
            <strong>
              {expenseAccount?.name ??
                "Unavailable — resolve the original purchase first"}
            </strong>
          </span>
          <span>
            Category: <strong>{category?.name ?? "—"}</strong>
          </span>
          <span>
            Original value:{" "}
            <strong>
              {purchase ? formatMyr(purchase.merchant_value_myr) : "—"}
            </strong>
          </span>
          <span>
            Already refunded:{" "}
            <strong>
              {purchase ? formatMyr(purchase.refunded_value_myr) : "—"}
            </strong>
          </span>
          <span>
            Remaining transaction value:{" "}
            <strong>
              {purchase
                ? formatMyr(purchase.refundable_remaining_myr ?? "0")
                : "—"}
            </strong>
          </span>
        </div>
        <fieldset className="wide fee-fields line-items">
          <legend>Returned assets</legend>
          {legs.map((leg, index) => (
            <div className="line-item" key={index}>
              <label>
                Receiving account {index + 1}
                <select
                  value={leg.account_id}
                  onChange={(event) =>
                    updateLeg(index, "account_id", event.target.value)
                  }
                  required
                >
                  <option value="">Select</option>
                  {accountOptions(accounts, "ASSET")}
                </select>
              </label>
              <label>
                Returned asset {index + 1}
                <select
                  value={leg.asset_id}
                  onChange={(event) =>
                    updateLeg(index, "asset_id", event.target.value)
                  }
                  required
                >
                  <option value="">Select</option>
                  {assetOptions(assets)}
                </select>
              </label>
              <label>
                Returned quantity {index + 1}
                <input
                  inputMode="decimal"
                  value={leg.quantity}
                  onChange={(event) =>
                    updateLeg(index, "quantity", event.target.value)
                  }
                  required
                />
              </label>
              <label>
                Transaction value MYR {index + 1}
                <input
                  inputMode="decimal"
                  value={leg.transaction_value_myr}
                  onChange={(event) =>
                    updateLeg(
                      index,
                      "transaction_value_myr",
                      event.target.value,
                    )
                  }
                  required
                />
              </label>
              <label>
                Reference value MYR {index + 1}
                <input
                  inputMode="decimal"
                  value={leg.reference_value_myr}
                  onChange={(event) =>
                    updateLeg(index, "reference_value_myr", event.target.value)
                  }
                  required
                />
              </label>
              {legs.length > 1 && (
                <button
                  className="text-button row-remove"
                  type="button"
                  onClick={() =>
                    setLegs((current) =>
                      current.filter((_item, rowIndex) => rowIndex !== index),
                    )
                  }
                >
                  Remove returned asset
                </button>
              )}
            </div>
          ))}
          <div className="row-actions">
            <button
              className="text-button"
              type="button"
              onClick={() =>
                setLegs((current) => [...current, emptyRefundLeg()])
              }
            >
              Add returned asset
            </button>
          </div>
        </fieldset>
        <div className="wide form-summary" role="status">
          <span>
            Transaction total: <strong>{transactionTotal}</strong>
          </span>
          <span>
            Reference total: <strong>{referenceTotal}</strong>
          </span>
          {overage && (
            <span className="field-error">
              Refund transaction total exceeds the remaining purchase value.
            </span>
          )}
        </div>
        {!purchases.length && (
          <div className="wide empty">
            No purchase currently has a refundable balance.
          </div>
        )}
        <div className="wide form-actions">
          <button
            className="primary"
            disabled={
              busy || !purchase || !expenseAccount || overage || !legsComplete
            }
          >
            Post refund
          </button>
        </div>
      </form>
    </>
  );
}

function RewardForms({
  assets,
  accounts,
  categories,
  cards,
  busy,
  onReward,
  onCreditReward,
}: Props) {
  const purchases = cards.filter(
    (card) =>
      card.transaction_type === "PURCHASE" && card.status !== "REVERSED",
  );
  const pending = useMemo(
    () =>
      purchases.flatMap((card) =>
        card.rewards
          .filter((reward) => reward.status === "PENDING")
          .map((reward) => ({ ...reward, merchant: card.merchant_name })),
      ),
    [purchases],
  );
  const [creditId, setCreditId] = useState("");
  const [creditValue, setCreditValue] = useState("");
  const [creditIncome, setCreditIncome] = useState("");
  const [creditCategory, setCreditCategory] = useState("");
  const [creditSource, setCreditSource] = useState("Credited price");
  const [creditedAt, setCreditedAt] = useState(localDateTimeValue());
  const selectedReward = pending.find((reward) => reward.id === creditId);
  const rate = derivedRate(creditValue, selectedReward?.amount ?? "");

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const value = values(form);
    const succeeded = await onReward(value("card_id"), {
      reward_type: value("reward_type"),
      account_id: value("account_id"),
      asset_id: value("asset_id"),
      amount: value("amount"),
      earned_at: new Date(value("earned_at")).toISOString(),
    });
    if (succeeded) resetSubmittedForm(form, "earned_at");
  }

  async function credit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedReward || !rate || !event.currentTarget.reportValidity())
      return;
    const succeeded = await onCreditReward(selectedReward.id, {
      income_account_id: creditIncome,
      category_id: creditCategory,
      value_myr: creditValue,
      valuation_source: creditSource,
      credited_at: new Date(creditedAt).toISOString(),
    });
    if (succeeded) {
      setCreditId("");
      setCreditValue("");
      setCreditIncome("");
      setCreditCategory("");
      setCreditSource("Credited price");
      setCreditedAt(localDateTimeValue());
    }
  }

  return (
    <>
      <div className="section-title">
        <div>
          <span className="eyebrow">PENDING ≠ CREDITED</span>
          <h2>Cashback and rewards</h2>
        </div>
      </div>
      <div className="split-forms reward-forms">
        <form className="compact-form" onSubmit={(event) => void add(event)}>
          <h3>Record pending reward</h3>
          <label>
            Purchase
            <select name="card_id" required>
              <option value="">Select</option>
              {purchases.map((card) => (
                <option value={card.id} key={card.id}>
                  {card.merchant_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Type
            <input name="reward_type" defaultValue="CASHBACK" required />
          </label>
          <label>
            Receiving account
            <select name="account_id" required>
              <option value="">Select</option>
              {accountOptions(accounts, "ASSET")}
            </select>
          </label>
          <label>
            Asset
            <select name="asset_id" required>
              <option value="">Select</option>
              {assetOptions(assets)}
            </select>
          </label>
          <label>
            Amount
            <input name="amount" inputMode="decimal" required />
          </label>
          <label>
            Earned at
            <input
              name="earned_at"
              type="datetime-local"
              defaultValue={localDateTimeValue()}
              required
            />
          </label>
          <button className="primary" disabled={busy}>
            Save pending
          </button>
        </form>
        <form className="compact-form" onSubmit={(event) => void credit(event)}>
          <h3>Credit reward</h3>
          <label>
            Pending reward
            <select
              aria-label="Pending reward"
              value={creditId}
              onChange={(event) => setCreditId(event.target.value)}
              required
            >
              <option value="">Select</option>
              {pending.map((reward) => (
                <option value={reward.id} key={reward.id}>
                  {reward.merchant} · {reward.amount}
                </option>
              ))}
            </select>
          </label>
          <label>
            Income account
            <select
              aria-label="Income account"
              value={creditIncome}
              onChange={(event) => setCreditIncome(event.target.value)}
              required
            >
              <option value="">Select</option>
              {accountOptions(accounts, "INCOME")}
            </select>
          </label>
          <label>
            Category
            <select
              aria-label="Reward category"
              value={creditCategory}
              onChange={(event) => setCreditCategory(event.target.value)}
              required
            >
              <option value="">Select</option>
              {categoryOptions(categories, "INCOME")}
            </select>
          </label>
          <label>
            Value MYR
            <input
              aria-label="Reward value MYR"
              inputMode="decimal"
              value={creditValue}
              onChange={(event) => setCreditValue(event.target.value)}
              required
            />
          </label>
          <label>
            Derived rate (MYR per asset)
            <input aria-label="Derived rate" value={rate} readOnly />
          </label>
          <label>
            Valuation source
            <input
              aria-label="Valuation source"
              value={creditSource}
              onChange={(event) => setCreditSource(event.target.value)}
              required
            />
          </label>
          <label>
            Credited at
            <input
              aria-label="Credited at"
              type="datetime-local"
              value={creditedAt}
              onChange={(event) => setCreditedAt(event.target.value)}
              required
            />
          </label>
          <button
            className="primary"
            disabled={busy || !selectedReward || !rate}
          >
            Post credited reward
          </button>
        </form>
      </div>
    </>
  );
}
