module.exports = {
  apps: [
    {
      name: 'jobobo-backend',
      script: 'app/main.py',
      interpreter: '/root/miniconda3/bin/python3',
      cwd: '/var/local/jobobo-backend',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        NODE_ENV: 'production',
        PYTHONPATH: '/var/local/jobobo-backend'
      },
      error_file: '/var/local/jobobo-backend/logs/pm2-error.log',
      out_file: '/var/local/jobobo-backend/logs/pm2-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss'
    }
  ]
};