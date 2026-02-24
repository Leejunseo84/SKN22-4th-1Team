-- Active: 1770790775308@@127.0.0.1@3306@mysql
-- 1. 데이터베이스 생성
DROP DATABASE IF EXISTS drug_db;
CREATE DATABASE drug_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 2. 서비스 전용 계정 생성 (계정명: drug_admin, 비밀번호: drug_pass123!)
-- 실 운영 환경에서는 비밀번호를 더 복잡하게 수정하세요.
CREATE USER IF NOT EXISTS 'drug'@'localhost' IDENTIFIED BY 'drug';

-- 3. 특정 DB(drug_db)에 대한 모든 권한 부여
GRANT ALL PRIVILEGES ON drug_db.* TO 'drug'@'localhost';

-- 4. 변경사항 즉시 반영
FLUSH PRIVILEGES;

-- 5. 생성된 계정 정보 확인 (선택 사항)
SELECT user, host FROM mysql.user WHERE user = 'drug';