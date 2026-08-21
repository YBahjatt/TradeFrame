import { useEffect, useState } from "react";

import { PricingProfile, TradeFrameSettings, api } from "../api";
import { useAsync } from "../components/useAsync";

const sourceOptions = ["no", "market_sell", "market_buy"];
const tfSourceOptions = ["market_sell", "market_buy"];
const methodOptions = ["high", "low", "average", "median"];
const roundingOptions = ["nearest", "up", "down"];

function label(value: string) {
  return value.replace("_", " ");
}

function ProfileSelect({
  profile,
  field,
  options,
  onChange,
}: {
  profile: PricingProfile;
  field: keyof PricingProfile;
  options: string[];
  onChange: (profile: PricingProfile) => void;
}) {
  return (
    <select
      className="w-full border border-slate-700 bg-slate-950 px-2 py-1"
      value={profile[field]}
      onChange={(event) => onChange({ ...profile, [field]: event.target.value })}
    >
      {options.map((option) => (
        <option key={option} value={option}>{label(option)}</option>
      ))}
    </select>
  );
}

function ProfileInput({
  profile,
  field,
  onChange,
}: {
  profile: PricingProfile;
  field: keyof PricingProfile;
  onChange: (profile: PricingProfile) => void;
}) {
  return (
    <input
      className="w-full border border-slate-700 bg-slate-950 px-2 py-1"
      value={profile[field]}
      onChange={(event) => onChange({ ...profile, [field]: event.target.value })}
    />
  );
}

export function SettingsPage() {
  const { data, error, loading } = useAsync(api.settings);
  const [settings, setSettings] = useState<TradeFrameSettings | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (data) setSettings(data);
  }, [data]);

  async function save() {
    if (!settings) return;
    setStatus("Saving");
    try {
      setSettings(await api.saveSettings(settings));
      setStatus("Saved");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    }
  }

  function updateProfile(name: "sell" | "buy" | "tf_calculations", profile: PricingProfile) {
    if (!settings) return;
    setSettings({ ...settings, [name]: profile });
  }

  if (loading || !settings) return <div>Loading settings</div>;
  if (error) return <div className="text-red-300">{error}</div>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Settings</h1>
          <div className="text-sm text-slate-400">Pricing, copy-message limits, and local data paths.</div>
        </div>
        <div className="flex items-center gap-3">
          {status && <div className="text-sm text-cyan-200">{status}</div>}
          <button type="button" onClick={save} className="border border-cyan-500 px-3 py-2 text-sm font-semibold text-cyan-100">
            Save
          </button>
        </div>
      </div>

      <section className="border border-slate-800 bg-slate-950 p-4">
        <div className="mb-3 font-semibold">Pricing</div>
        <div className="overflow-auto border border-slate-800">
          <table className="min-w-[760px] w-full text-sm">
            <thead className="bg-slate-900 text-left">
              <tr>
                <th className="px-3 py-2"></th>
                <th className="px-3 py-2">Sell</th>
                <th className="px-3 py-2">Buy</th>
                <th className="px-3 py-2">TF Calculations</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-slate-800">
                <td className="px-3 py-2 text-slate-300">Show price / source</td>
                <td className="px-3 py-2"><ProfileSelect profile={settings.sell} field="price_source" options={sourceOptions} onChange={(profile) => updateProfile("sell", profile)} /></td>
                <td className="px-3 py-2"><ProfileSelect profile={settings.buy} field="price_source" options={sourceOptions} onChange={(profile) => updateProfile("buy", profile)} /></td>
                <td className="px-3 py-2"><ProfileSelect profile={settings.tf_calculations} field="price_source" options={tfSourceOptions} onChange={(profile) => updateProfile("tf_calculations", profile)} /></td>
              </tr>
              <tr className="border-t border-slate-800">
                <td className="px-3 py-2 text-slate-300">Calculation method</td>
                <td className="px-3 py-2"><ProfileSelect profile={settings.sell} field="calculation_method" options={methodOptions} onChange={(profile) => updateProfile("sell", profile)} /></td>
                <td className="px-3 py-2"><ProfileSelect profile={settings.buy} field="calculation_method" options={methodOptions} onChange={(profile) => updateProfile("buy", profile)} /></td>
                <td className="px-3 py-2"><ProfileSelect profile={settings.tf_calculations} field="calculation_method" options={methodOptions} onChange={(profile) => updateProfile("tf_calculations", profile)} /></td>
              </tr>
              <tr className="border-t border-slate-800">
                <td className="px-3 py-2 text-slate-300">Margin</td>
                <td className="px-3 py-2"><ProfileInput profile={settings.sell} field="margin" onChange={(profile) => updateProfile("sell", profile)} /></td>
                <td className="px-3 py-2"><ProfileInput profile={settings.buy} field="margin" onChange={(profile) => updateProfile("buy", profile)} /></td>
                <td className="px-3 py-2"><ProfileInput profile={settings.tf_calculations} field="margin" onChange={(profile) => updateProfile("tf_calculations", profile)} /></td>
              </tr>
              <tr className="border-t border-slate-800">
                <td className="px-3 py-2 text-slate-300">Rounding</td>
                <td className="px-3 py-2"><ProfileSelect profile={settings.sell} field="rounding" options={roundingOptions} onChange={(profile) => updateProfile("sell", profile)} /></td>
                <td className="px-3 py-2"><ProfileSelect profile={settings.buy} field="rounding" options={roundingOptions} onChange={(profile) => updateProfile("buy", profile)} /></td>
                <td className="px-3 py-2"><ProfileSelect profile={settings.tf_calculations} field="rounding" options={roundingOptions} onChange={(profile) => updateProfile("tf_calculations", profile)} /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="border border-slate-800 bg-slate-950 p-4">
        <div className="mb-3 font-semibold">TradeFrame Settings</div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <div className="text-slate-400">WF max chat message length</div>
            <input className="w-full border border-slate-700 bg-slate-950 px-3 py-2" type="number" value={settings.warframe_chat_max_length} onChange={(event) => setSettings({ ...settings, warframe_chat_max_length: Number(event.target.value) })} />
          </label>
          <label className="space-y-1 text-sm">
            <div className="text-slate-400">Reserved characters for your own text</div>
            <input className="w-full border border-slate-700 bg-slate-950 px-3 py-2" type="number" value={settings.warframe_chat_margin} onChange={(event) => setSettings({ ...settings, warframe_chat_margin: Number(event.target.value) })} />
          </label>
          <label className="space-y-1 text-sm md:col-span-2">
            <div className="text-slate-400">AlecaFrame data directory</div>
            <input className="w-full border border-slate-700 bg-slate-950 px-3 py-2" value={settings.aleca_data_dir} onChange={(event) => setSettings({ ...settings, aleca_data_dir: event.target.value })} />
            <div className="text-xs text-slate-500">
              This is AlecaFrame's local user data folder that contains files like lastData.dat, not the Overwolf/AlecaFrame installation folder.
            </div>
            <div className={settings.aleca_data_dir_valid ? "text-xs text-emerald-300" : "text-xs text-amber-300"}>
              {settings.aleca_data_dir_status}
            </div>
          </label>
        </div>
        <div className="mt-3 text-sm text-slate-400">Copied text always appends fixed text: via TradeFrame</div>
      </section>
    </div>
  );
}
