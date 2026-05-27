on run
	do shell script "cd " & quoted form of POSIX path of "/Users/anzhen/Documents/定点截图软件-项目" & " && export TK_SILENCE_DEPRECATION=1 && /usr/bin/python3 " & quoted form of POSIX path of "/Users/anzhen/Documents/定点截图软件-项目/定格截图.py" & " >/tmp/定格截图.log 2>&1 &"
end run
