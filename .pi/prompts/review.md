Review the VirtueMart product importer project at ~/Projects/liberti-product-plugin.   
                                                                                          
   READ-ONLY TASK. Do not modify, create, or delete anything. Do not run the importer.    
 Minimize token use — no full file dumps in your answers.                                 
                                                                                          
   CONTEXT (verified earlier):                                                            
   - Target: MariaDB 11.4 / Joomla 5.4.8 / VirtueMart 4.8.0, DB "manouka_manouka_",       
 prefix xhngw_                                                                            
   - Importer: vmimporter/ package, importer.py CLI, 44 tests green, dry-run default,     
 per-product transactions, --create-only flag                                             
   - Schema docs: docs/virtuemart-database-analysis.md, docs/pre-production-audit.md      
                                                                                          
   DEPLOYMENT MODEL (no SSH available; HestiaCP shared hosting, panel user "manouka"):    
   - The importer is FTP-uploaded as server-bundle/ to                                    
 /home/manouka/web/libertidance.com/import-bundle/ (outside public_html, not              
 web-accessible). PyMySQL is vendored in server-bundle/vendor/ because pip/venv is        
 unavailable on the server.                                                               
   - Execution happens via Hestia CRON one-shot jobs: bash                                
 /home/manouka/web/libertidance.com/import-bundle/run-dry-run.sh (read-only, tees output  
 to dryrun-out.txt) and run-import.sh (gated by APPROVED=YES inside the script; uses      
 --yes since cron has no TTY).                                                            
   - Logs are downloaded back over FTP (dryrun-out.txt, import-out.txt,                   
 logs/import-*.log); verification happens in Joomla admin + phpMyAdmin (DB user           
 manouka_antima_@localhost).                                                              
   - DB access from outside the server is impossible (MariaDB localhost-only); dry-runs   
 against production worked and were server-enforced read-only.                            
   - Workflow per batch: upload CSV+images via FileZilla → one-shot cron dry-run →        
 FTP-download output → human review → flip APPROVED=YES → one-shot cron import → verify → 
 delete cron job.                                                                         
                                                                                          
   Do exactly two things:                                                                 
                                                                                          
   1. PROJECT REVIEW (no changes):                                                        
      - Skim the code (vmimporter/, tools/, tests/) and docs. Don't quote.                
      - Identify: architectural weaknesses, safety gaps, dead code, fragile tooling,      
 missing tests, docs drift, weaknesses of the FTP/cron deployment model itself.           
      - Rank findings: critical / important / nice-to-have. One line each. No fixes, just 
 findings.                                                                                
                                                                                          
   2. CSV READINESS ASSESSMENT for the real site:                                         
      - For products.danceyou.csv, products.grishko.csv, products.capezio.csv run the     
 importer's own validation (vmimporter.products_csv.parse_csv) in a throwaway python      
 snippet against the local sqlite copy (local/vm_analysis.db) — read-only, NO --import.   
      - Report per file: row count, rows passing validation, validation errors grouped by 
 type, rows with title==sku or empty title, empty prices / sizes / colours /              
 descriptions, duplicate SKUs, SKUs that already exist in the live DB copy (creates-only  
 collisions).                                                                             
      - Per-file verdict: ready for dry-run / needs data / needs decisions, plus the      
 minimal data that must be filled before a first small real import.                       
                                                                                          
   Finish with a single combined go/no-go recommendation for a first 3-product test       
 import, and list anything that must be confirmed with the Joomla developer first. 