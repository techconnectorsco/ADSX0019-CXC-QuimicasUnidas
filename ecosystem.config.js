module.exports = {
    apps: [
        {
            name: "api-rpa-cxc",
            script: "api.py",
            cwd: "C:/Quimicas_Unidas/ADSX0019-CXC-QuimicasUnidas",
            interpreter: "C:/Quimicas_Unidas/ADSX0019-CXC-QuimicasUnidas/.venv/Scripts/pythonw.exe",
            instances: 1,
            exec_mode: "fork",
            watch: false,
            max_restarts: 4,
            min_uptime: "10s"
        },
        {
            name: "ngrok-tunnel",
            script: "C:/Ngrok/ngrok.exe",
            // 🔥 Cambiado al final: se fuerza el uso de 127.0.0.1:8050 en lugar de solo 8050
            args: "http --url=statistic-auction-snowstorm.ngrok-free.dev 127.0.0.1:8050",
            instances: 1,
            exec_mode: "fork",
            watch: false,
            max_restarts: 4,
            min_uptime: "10s"
        }
    ]
};