import { useState, useEffect, type FormEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { api, type HoldingPayload } from "../../lib/api";

interface Props {
  open: boolean;
  mode: "add" | "edit";
  initial?: { ticker: string; shares?: number; entry_price?: number; entry_date?: string; entry_score?: number; note?: string } | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function HoldingFormModal({ open, mode, initial, onClose, onSaved }: Props) {
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [entryPrice, setEntryPrice] = useState("");
  const [entryDate, setEntryDate] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setSubmitting(false);
    if (mode === "edit" && initial) {
      setTicker(initial.ticker);
      setShares(initial.shares?.toString() ?? "");
      setEntryPrice(initial.entry_price?.toString() ?? "");
      setEntryDate(initial.entry_date ?? "");
      setNote(initial.note ?? "");
    } else {
      setTicker("");
      setShares("");
      setEntryPrice("");
      setEntryDate(localDateISO());
      setNote("");
    }
  }, [open, mode, initial]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const sharesNum = parseFloat(shares);
    const priceNum = parseFloat(entryPrice);
    if (!ticker.trim()) return setError("Ticker is required");
    if (isNaN(sharesNum) || sharesNum <= 0) return setError("Shares must be a positive number");
    if (isNaN(priceNum) || priceNum <= 0) return setError("Entry price must be a positive number");

    const body: HoldingPayload = {
      shares: sharesNum,
      entry_price: priceNum,
      entry_date: entryDate || undefined,
      note: note.trim() || undefined,
    };

    setSubmitting(true);
    try {
      if (mode === "add") {
        await api.createHolding(ticker.trim().toUpperCase(), body);
      } else {
        await api.updateHolding(ticker, body);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

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
              <h2 className="text-base font-bold text-text-primary">
                {mode === "add" ? "Add Holding" : `Edit ${ticker}`}
              </h2>
              <button
                type="button"
                onClick={onClose}
                className="text-text-muted hover:text-text-primary transition-colors"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-4 space-y-3">
              <Field label="Ticker">
                <input
                  type="text"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  disabled={mode === "edit"}
                  placeholder="e.g. AAPL"
                  className={inputCls + (mode === "edit" ? " opacity-60 cursor-not-allowed" : "")}
                  autoFocus={mode === "add"}
                  maxLength={8}
                />
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Shares">
                  <input
                    type="number"
                    step="any"
                    value={shares}
                    onChange={(e) => setShares(e.target.value)}
                    className={inputCls}
                    autoFocus={mode === "edit"}
                  />
                </Field>
                <Field label="Entry Price">
                  <input
                    type="number"
                    step="any"
                    value={entryPrice}
                    onChange={(e) => setEntryPrice(e.target.value)}
                    className={inputCls}
                  />
                </Field>
              </div>

              <Field label="Entry Date">
                <input
                  type="date"
                  value={entryDate}
                  onChange={(e) => setEntryDate(e.target.value)}
                  className={inputCls}
                />
              </Field>

              <Field label="Note (optional)">
                <input
                  type="text"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. Sold 5 shares @ $101 on 2026-04-06"
                  className={inputCls}
                />
              </Field>

              {error && (
                <div className="text-xs text-danger bg-danger/10 border border-danger/30 rounded px-3 py-2">
                  {error}
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="flex-1 px-4 py-2 rounded-lg border border-border text-text-secondary hover:text-text-primary hover:border-text-muted transition-colors text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 px-4 py-2 rounded-lg bg-accent text-base font-semibold hover:bg-accent/90 disabled:opacity-50 disabled:cursor-wait transition-colors text-sm"
                  style={{ color: "var(--color-base)" }}
                >
                  {submitting ? "Saving..." : mode === "add" ? "Add" : "Save"}
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function localDateISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const inputCls =
  "w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-1">
        {label}
      </span>
      {children}
    </label>
  );
}
