CREATE DATABASE IF NOT EXISTS tradeframe
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'tradeframe_user'@'localhost' IDENTIFIED BY 'tradeframe_dev_password';
GRANT ALL PRIVILEGES ON tradeframe.* TO 'tradeframe_user'@'localhost';
FLUSH PRIVILEGES;
