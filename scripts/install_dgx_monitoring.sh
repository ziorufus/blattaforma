#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Errore: eseguire con sudo: sudo bash $0" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "Errore: systemd/systemctl non disponibile." >&2
  exit 1
fi
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "Errore: nvidia-smi non disponibile. Installare i driver NVIDIA prima di procedere." >&2
  exit 1
fi

METRICS_DIR=/var/lib/prometheus/node-exporter
NODE_EXPORTER_SERVICE=prometheus-node-exporter.service

# Installazione tramite pacchetti Ubuntu/Debian, se necessario.
if ! command -v apt-get >/dev/null 2>&1; then
  echo "Errore: installer supportato su Ubuntu/Debian (apt-get richiesto)." >&2
  exit 1
fi
if systemctl list-unit-files --no-legend node_exporter.service 2>/dev/null | grep -q '^node_exporter.service'; then
  echo "Errore: rilevato node_exporter.service personalizzato. Non installo una seconda istanza sulla porta 9100." >&2
  echo "Configurare manualmente il textfile collector nell'istanza esistente." >&2
  exit 1
fi
if ! dpkg-query -W -f='${Status}' prometheus-node-exporter 2>/dev/null | grep -qx 'install ok installed'; then
  if command -v node_exporter >/dev/null 2>&1 || command -v prometheus-node-exporter >/dev/null 2>&1; then
    echo "Errore: node_exporter gia presente fuori dal pacchetto apt. Evito installazioni duplicate." >&2
    exit 1
  fi
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y prometheus-node-exporter
fi

cat > /usr/local/bin/export_gpu_metrics.sh <<'GPU_SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/var/lib/prometheus/node-exporter/gpu.prom
mkdir -p "$(dirname "$OUT")"
TMP=$(mktemp "${OUT}.tmp.XXXXXXXX")
trap 'rm -f "$TMP"' EXIT

# Come nella configurazione originale, esporta la prima GPU.
GPU_LINE=$(nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,power.draw --format=csv,noheader,nounits | head -n 1)
IFS=',' read -r utilization temperature power <<< "$GPU_LINE"
utilization=$(echo "$utilization" | xargs)
temperature=$(echo "$temperature" | xargs)
power=$(echo "$power" | xargs)

for value in "$utilization" "$temperature" "$power"; do
  if ! [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "Errore: metrica GPU non valida: $value" >&2
    exit 1
  fi
done

cat > "$TMP" <<EOF
# HELP gpu_utilization_ratio GPU utilization ratio.
# TYPE gpu_utilization_ratio gauge
gpu_utilization_ratio $(awk -v u="$utilization" 'BEGIN {printf "%.6f", u / 100}')
# HELP gpu_temperature_celsius GPU temperature.
# TYPE gpu_temperature_celsius gauge
gpu_temperature_celsius $temperature
# HELP gpu_power_watts GPU power consumption.
# TYPE gpu_power_watts gauge
gpu_power_watts $power
EOF
chmod 644 "$TMP"
mv -f "$TMP" "$OUT"
GPU_SCRIPT
chmod 755 /usr/local/bin/export_gpu_metrics.sh

cat > /etc/systemd/system/export-gpu-metrics.service <<'EOF'
[Unit]
Description=Esporta metriche GPU per node_exporter

[Service]
Type=oneshot
ExecStart=/usr/local/bin/export_gpu_metrics.sh
EOF

cat > /etc/systemd/system/export-gpu-metrics.timer <<'EOF'
[Unit]
Description=Esegue periodicamente export_gpu_metrics.sh

[Timer]
OnBootSec=10s
OnUnitActiveSec=10s
AccuracySec=1s
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/ollama-retry.timer <<'EOF'
[Unit]
Description=Retry Ollama startup every minute

[Timer]
OnBootSec=1min
OnUnitInactiveSec=1min
Unit=ollama.service
AccuracySec=5s

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/nginx-retry.timer <<'EOF'
[Unit]
Description=Retry nginx startup every minute

[Timer]
OnBootSec=1min
OnUnitInactiveSec=1min
Unit=nginx.service
AccuracySec=5s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now export-gpu-metrics.timer
systemctl enable --now ollama-retry.timer
systemctl enable --now nginx-retry.timer

# Prima esportazione senza attendere la scadenza del timer.
if systemctl start export-gpu-metrics.service; then
  echo "Metriche GPU scritte in $METRICS_DIR/gpu.prom"
else
  echo "Attenzione: esportazione GPU iniziale fallita. Vedere: journalctl -u export-gpu-metrics.service" >&2
fi

echo
echo '=== Timer installati ==='
systemctl list-timers --all export-gpu-metrics.timer ollama-retry.timer nginx-retry.timer --no-pager

echo
echo 'NOTA: node_exporter deve essere configurato separatamente con'
echo "  --collector.textfile.directory=$METRICS_DIR"
echo 'Installazione completata.'
