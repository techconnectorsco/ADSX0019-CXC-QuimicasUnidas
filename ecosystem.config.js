module.exports = {
  apps: [
    {
      name: "api-rpa-cxc",
      script: "api.py",
      cwd: "C:/Quimicas_Unidas/ADSX0019-CXC-QuimicasUnidas",
      // Cambiado a barras normales / 
      // ⚠️ NOTA: Si tu carpeta se llama 'venv' sin punto, cámbialo aquí abajo
      interpreter: "C:/Quimicas_Unidas/ADSX0019-CXC-QuimicasUnidas/.venv/Scripts/python.exe", 
      instances: 1, 
      exec_mode: "fork",
      watch: false
    },
    {
      name: "ngrok-tunnel",
      script: "cmd",
      args: "/c ngrok http --domain=statistic-auction-snowstorm.ngrok-free.dev 8050",
      cwd: "C:/Quimicas_Unidas/ADSX0019-CXC-QuimicasUnidas",
      instances: 1,
      exec_mode: "fork",
      watch: false
    }
  ]
};