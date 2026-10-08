(function(){if(!document.body.classList.contains('present'))return;
var s=[document.querySelector('.hero')].concat([].slice.call(document.querySelectorAll('section')));
function at(){var y=window.scrollY+window.innerHeight/2,i=0;s.forEach(function(el,k){if(el.offsetTop<=y)i=k});return i}
document.addEventListener('keydown',function(ev){var d=0;if(['ArrowRight','ArrowDown','PageDown',' '].indexOf(ev.key)>=0)d=1;
if(['ArrowLeft','ArrowUp','PageUp'].indexOf(ev.key)>=0)d=-1;if(!d)return;ev.preventDefault();
var t=s[Math.max(0,Math.min(s.length-1,at()+d))];window.scrollTo({top:t.offsetTop,behavior:'smooth'})})})();
