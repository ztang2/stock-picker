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

export default function AddSharesModal({ open, ticker, holding, currentPrice, onClose, onSaved }: Props) {
  const [addedShares, setAddedShares] = useState("");
  const [addedPrice, setAddedPrice] = useState("");
  const [addedDate, setAddedDate] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setSubmitting(false);
    setAddedShares("");
    setAddedPrice(currentPrice ? currentPrice.toFixed(2) : "");
    setAddedDate(localDateISO());
    setNote("");
  }, [open, currentPrice]);

  if (!ticker || !holding) return null;

  const oldShares = holding.shares ?? 0;
  const oldPrice = holding.entry_price ?? 0;
  const addedN = parseFloat(addedShares);
  const addedP = parseFloat(addedPrice);

  const totalShares =
    !isNaN(addedN) && addedN > 0 ? oldShares + addedN : null;
  const newAvg =
    !isNaN(addedN) && addedN > 0 && !isNaN(addedP) && addedP > 0 && totalShares
      ? (oldShares * oldPrice + addedN * addedP) / totalShares
      : null;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (isNaN(addedN) || addedN <= 0) return setError("Shares must be positive");
    if (isNaN(addedP) || addedP <= 0) return setError("Price must be positive");
    if (!addedDate) return setError("Date required");

    setSubmitting(true);
    try {
      await api.addSharesToHolding(ticker!, {
        added_shares: addedN,
        added_price: addedP,
        added_date: addedDate,
        note: note.trim() || undefined,
      });
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
              <h2 className="text-base font-bold text-text-primary">Add Shares to {ticker}</h2>
              <button type="button" onClick={onClose} className="text-text-muted hover:text-text-primary" aria-label="Close">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-4 space-y-3">
              <div className="grid grid-cols-3 gap-2 p-3 rounded-lg bg-base border border-border-subtle text-xs">
                <Stat label="Current" value={`${oldShares.toFixed(4)} sh`} />
                <Stat label="Avg Entry" value={`$${oldPrice.toFixed(2)}`} />
                <Stat label="Since" value={holding.entry_date ?? "—"} />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Add Shares">
                  <input
                    type="number"
                    step="any"
                    value={addedShares}
                    onChange={(e) => setAddedShares(e.target.value)}
                    className={inputCls}
                    autoFocus
                    placeholder="e.g. 5"
                  />
                </Field>
                <Field label="Price">
                  <input
                    type="number"
                    step="any"
                    value={addedPrice}
                    onChange={(e) => setAddedPrice(e.target.value)}
                    className={inputCls}
                  />
                </Field>
              </div>

              <Field label="Purchase Date">
                <input
                  type="date"
                  value={addedDate}
                  onChange={(e) => setAddedDate(e.target.value)}
                  className={inputCls}
                />
              </Field>

              <Field label="Note (optional)">
                <input
                  type="text"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. averaging down after earnings dip"
                  className={inputCls}
                />
              </Field>

              {totalShares != null && newAvg != null && (
                <div className="p-3 rounded-lg bg-base border border-border-subtle space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-text-muted text-xs uppercase tracking-wider">New Total</span>
                    <span className="font-data text-text-primary">{totalShares.toFixed(4)} sh</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted text-xs uppercase tracking-wider">New Avg Entry</span>
                    <span className="font-data font-bold text-accent">${newAvg.toFixed(2)}</span>
                  </div>
                  {oldPrice > 0 && (
                    <div className="flex justify-between text-[11px] text-text-muted">
                      <span>Cost basis shift</span>
                      <span className="font-data">
                        ${oldPrice.toFixed(2)} → ${newAvg.toFixed(2)}{" "}
                        ({newAvg >= oldPrice ? "+" : ""}{(((newAvg - oldPrice) / oldPrice) * 100).toFixed(2)}%)
                      </span>
                    </div>
                  )}
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
                  {submitting ? "Saving..." : "Add Shares"}
                </button>
              </div>
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
