interface SynthesisBannerProps {
  text: string | undefined;
}

export default function SynthesisBanner({ text }: SynthesisBannerProps) {
  if (!text) return null;

  return (
    <div className="mx-6 my-4 p-4 rounded-xl bg-gradient-to-br from-positive/5 to-accent/5 border border-positive/20">
      <div className="text-[11px] uppercase tracking-wider text-positive font-bold mb-1.5">
        AI Synthesis
      </div>
      <div className="text-[13px] text-text-primary leading-relaxed">{text}</div>
    </div>
  );
}
