import { useState, useEffect, type FormEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { api, type HoldingRecord } from "../../lib/api";

interface Props {
  open: boolean;
  ticker: string | null;
  holding: HoldingRecord | null;
  currentPrice?: number;
  onClose: () => void;
  onSaved: () => void;
}

export default function SellModal({ open, ticker, holding, currentPrice, onClose, onSaved }: Props) {
  const [exitPrice, setExitPrice] = useState("");
  const [exitDate, setExitDate] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setSubmitting(false);
    setExitPrice(currentPrice ? currentPrice.toFixed(2) : "");
    setExitDate(localDateISO());
    setNote("");
  }, [open, currentPrice]);

  if (!ticker || !holding) return null;

  const shares = holding.shares ?? 0;
  const entryPrice = holding.entry_price ?? 0;
  const exitNum = parseFloat(exitPrice);
  const pnl = !isNaN(exitNum) ? (exitNum - entryPrice) * shares : null;
  const pnlPct = !isNaN(exitNum) && entryPrice > 0 ? ((exitNum - entryPrice) / entryPrice) * 100 : null;

  async function handleRecordSale(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (isNaN(exitNum) || exitNum <= 0) return setError("Exit price must be positive");
    if (!exitDate) return setError("Exit date required");

    setSubmitting(true);
    try {
      await api.closeHolding(ticker!, { exit_price: exitNum, exit_date: exitDate, note: note.trim() || undefined });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDiscard() {
    if (!window.confirm(`Discard ${ticker} without recording the sale? Archive won't be updated.`)) return;
    setError(null);
    setSubmitting(true);
    try {
      await api.deleteHolding(ticker!);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  const pnlColor = pnl != null ? (pnl >= 0 ? "text-positive" : "text-danger") : "text-text-muted";

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-xl bg-base/80"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.96, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.96, y: 8 }}
            className="w-full max-w-md bg-surface border border-border rounded-xl shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-border">
              <h2 className="text-base font-bold text-text-primary">Sell {ticker}</h2>
              <button type="button" onClick={onClose} className="text-text-muted hover:text-text-primary" aria-label="Close">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleRecordSale} className="p-4 space-y-3">
              <div className="grid grid-cols-3 gap-2 p-3 rounded-lg bg-base border border-border-subtle text-xs">
                <Stat label="Shares" value={shares.toFixed(4)} />
                <Stat label="Entry" value={`$${entryPrice.toFixed(2)}`} />
                <Stat label="Entry Date" value={holding.entry_date ?? "—"} />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Exit Price">
                  <input
                    type="number"
                    step="any"
                    value={exitPrice}
                    onChange={(e) => setExitPrice(e.target.value)}
                    className={inputCls}
                    autoFocus
                  />
                </Field>
                <Field label="Exit Date">
                  <input
                    type="date"
                    value={exitDate}
                    onChange={(e) => setExitDate(e.target.value)}
                    className={inputCls}
                  />
                </Field>
              </div>

              <Field label="Note (optional)">
                <input
                  type="text"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. Took profits ahead of earnings"
                  className={inputCls}
                />
              </Field>

              {pnl != null && (
                <div className="p-3 rounded-lg bg-base border border-border-subtle text-sm flex items-center justify-between">
                  <span className="text-text-muted text-xs uppercase tracking-wider">Realized P&amp;L</span>
                  <span className={`font-bold font-data ${pnlColor}`}>
                    {pnl >= 0 ? "+" : ""}${pnl.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    {pnlPct != null && (
                      <span className="ml-2 text-xs">
                        ({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%)
                      </span>
                    )}
                  </span>
                </div>
              )}

              {error && (
                <div className="text-xs text-danger bg-danger/10 border border-danger/30 rounded px-3 py-2">
                  {error}
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="flex-1 px-4 py-2 rounded-lg border border-border text-text-secondary hover:text-text-primary hover:border-text-muted text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 px-4 py-2 rounded-lg bg-accent font-semibold hover:bg-accent/90 disabled:opacity-50 text-sm"
                  style={{ color: "var(--color-base)" }}
                >
                  {submitting ? "Saving..." : "Record Sale"}
                </button>
              </div>

              <button
                type="button"
                onClick={handleDiscard}
                disabled={submitting}
                className="w-full text-center text-[11px] text-text-muted hover:text-danger transition-colors pt-1"
              >
                Discard without recording (erroneous add)
              </button>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

const inputCls =
  "w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-1">{label}</span>
      {children}
    </label>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">{label}</div>
      <div className="text-[13px] font-data text-text-primary">{value}</div>
    </div>
  );
}

function localDateISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
