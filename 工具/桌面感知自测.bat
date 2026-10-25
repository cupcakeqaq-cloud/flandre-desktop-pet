@echo off
chcp 936 >nul
title 桌面感知验收（催休息压成 3 分钟）
cd /d "%~dp0.."
set "FLANDRE_STREAK_TEST=180"
echo 这次启动后，连续动 3 分钟她就会催你去休息（正常是 50 分钟）。
echo.
echo 1) 先看设置里「芙兰看见你在干什么」的总开关是开着的
echo 2) 打开记事本随便敲字、或者动动鼠标，别停超过 1 分钟
echo 3) 3 分钟后她该说一句「连着忙了 3 分钟」那种话
echo.
echo 平时用双击 芙兰朵露.exe 就行，不用开这个。
echo.
start "" "芙兰朵露.exe"
