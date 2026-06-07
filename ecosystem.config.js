module.exports = {
    apps: [
        {
            name: "api-rpa-cxc",
            script: "api.py",
            cwd: "D:\\Users\\Usuario\\Desktop\\Quimicas-Unidas",
            interpreter: "D:\\Users\\Usuario\\Desktop\\Quimicas-Unidas\\.venv\\Scripts\\python.exe",
            instances: 1,
            exec_mode: "fork",
            watch: false
        },
        {
            name: "ngrok-tunnel",
            script: "ngrok",
            // Aquí colocamos tu dominio estático de la captura y tu puerto 8050
            args: "http --domain=statistic-auction-snowstorm.ngrok-free.dev 8050",
            exec_mode: "fork",
            instances: 1,
            watch: false
        }
    ]
};